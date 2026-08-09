import json
import logging
import os
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from io import StringIO

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    ArtifactId,
    DatasetId,
    RequestId,
    RunId,
)
from ea_research_lab.infrastructure.config import (
    ConfigurationError,
    Settings,
    load_settings,
)
from ea_research_lab.infrastructure.logging import (
    LOGGER_NAME,
    configure_logging,
    log_event,
)


class ConfigurationTests(unittest.TestCase):
    def test_defaults_environment_and_explicit_precedence_are_deterministic(self) -> None:
        environment = {
            "EA_RESEARCH_LAB_LOG_LEVEL": "WARNING",
            "EA_RESEARCH_LAB_LOG_FORMAT": "text",
        }
        original_environment = dict(os.environ)
        supplied_environment = environment.copy()

        self.assertEqual(load_settings(environ={}), Settings())
        self.assertEqual(
            load_settings(environ=environment),
            Settings(log_level="WARNING", log_format="text"),
        )
        self.assertEqual(
            load_settings(
                log_level="DEBUG",
                log_format="json",
                environ=environment,
            ),
            Settings(log_level="DEBUG", log_format="json"),
        )
        self.assertEqual(environment, supplied_environment)
        self.assertEqual(dict(os.environ), original_environment)

    def test_settings_are_frozen_and_invalid_values_fail_safely(self) -> None:
        settings = Settings()
        with self.assertRaises(FrozenInstanceError):
            settings.log_level = "DEBUG"

        cases = (
            {"log_level": "verbose"},
            {"log_format": "yaml"},
            {"environ": {"EA_RESEARCH_LAB_LOG_LEVEL": ""}},
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ConfigurationError) as caught:
                    load_settings(**arguments)
                self.assertEqual(caught.exception.code, "invalid_configuration")
                self.assertNotIn("verbose", str(caught.exception))
                self.assertNotIn("yaml", str(caught.exception))

    def test_import_has_no_logging_configuration_side_effect(self) -> None:
        script = (
            "import logging; "
            f"logger = logging.getLogger({LOGGER_NAME!r}); "
            "before = (list(logger.handlers), logger.level, logger.propagate); "
            "import ea_research_lab.infrastructure.config; "
            "import ea_research_lab.infrastructure.logging; "
            "after = (list(logger.handlers), logger.level, logger.propagate); "
            "raise SystemExit(0 if before == after else 1)"
        )
        completed = subprocess.run([sys.executable, "-c", script], check=False)
        self.assertEqual(completed.returncode, 0)


class OperationalLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger(LOGGER_NAME)
        self.original_handlers = self.logger.handlers[:]
        self.original_level = self.logger.level
        self.original_propagate = self.logger.propagate
        self.logger.handlers = []

    def tearDown(self) -> None:
        for handler in self.logger.handlers:
            if handler not in self.original_handlers:
                handler.close()
        self.logger.handlers = self.original_handlers
        self.logger.setLevel(self.original_level)
        self.logger.propagate = self.original_propagate

    def test_json_event_has_controlled_shape_and_safe_context(self) -> None:
        stream = StringIO()
        logger = configure_logging(Settings(), stream=stream)
        request_id = new_entity_id(RequestId)
        context = RequestContext(request_id, "research-client")
        error = ApplicationError(
            ApplicationErrorCode.INVALID_VALUE,
            "The request is invalid.",
            details={"opaque_sut_payload": "sensitive-value"},
            request_id=request_id,
            cause=RuntimeError("internal-cause-detail"),
        )

        log_event(
            logger,
            logging.ERROR,
            "request.rejected",
            "Request validation failed.",
            context=context,
            run_id=new_entity_id(RunId),
            artifact_id=new_entity_id(ArtifactId),
            dataset_id=new_entity_id(DatasetId),
            analysis_result_id=new_entity_id(AnalysisResultId),
            error=error,
        )

        serialized = stream.getvalue()
        record = json.loads(serialized)
        self.assertEqual(record["level"], "ERROR")
        self.assertEqual(record["logger"], LOGGER_NAME)
        self.assertEqual(record["event"], "request.rejected")
        self.assertEqual(record["message"], "Request validation failed.")
        self.assertEqual(record["request_id"], str(request_id))
        self.assertEqual(record["caller_id"], "research-client")
        self.assertEqual(record["error_code"], "invalid_value")
        self.assertTrue(record["run_id"].startswith("run_"))
        self.assertTrue(record["artifact_id"].startswith("artifact_"))
        self.assertTrue(record["dataset_id"].startswith("dataset_"))
        self.assertTrue(record["analysis_result_id"].startswith("analysisresult_"))
        timestamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        self.assertEqual(timestamp.tzinfo, UTC)
        self.assertNotIn("sensitive-value", serialized)
        self.assertNotIn("internal-cause-detail", serialized)
        self.assertNotIn("details", record)

    def test_formatter_ignores_arbitrary_extra_fields_and_exception_details(self) -> None:
        stream = StringIO()
        logger = configure_logging(Settings(), stream=stream)
        try:
            raise RuntimeError("private-exception-detail")
        except RuntimeError:
            logger.error(
                "Operation failed safely.",
                extra={
                    "event_name": {"secret": "event-detail"},
                    "sut_inputs": {"secret": "opaque-input"},
                    "raw_evidence_payload": "raw-content",
                },
                exc_info=True,
            )

        serialized = stream.getvalue()
        record = json.loads(serialized)
        self.assertEqual(record["event"], "operational.message")
        self.assertNotIn("sut_inputs", record)
        self.assertNotIn("raw_evidence_payload", record)
        self.assertNotIn("event-detail", serialized)
        self.assertNotIn("opaque-input", serialized)
        self.assertNotIn("raw-content", serialized)
        self.assertNotIn("private-exception-detail", serialized)

    def test_configuration_is_idempotent_and_text_format_remains_structured(self) -> None:
        stream = StringIO()
        first = configure_logging(Settings(), stream=stream)
        second = configure_logging(Settings(log_format="text"), stream=stream)

        self.assertIs(first, second)
        self.assertEqual(len(self.logger.handlers), 1)
        log_event(second, logging.INFO, "foundation.ready", "Foundation is ready.")
        line = stream.getvalue()
        self.assertIn('event="foundation.ready"', line)
        self.assertIn('message="Foundation is ready."', line)

    def test_log_event_rejects_invalid_context_and_event_names(self) -> None:
        logger = configure_logging(Settings(), stream=StringIO())
        with self.assertRaises(ValueError):
            log_event(logger, logging.INFO, "Invalid Event", "Message.")
        with self.assertRaises(TypeError):
            log_event(
                logger,
                logging.INFO,
                "request.received",
                "Message.",
                run_id=new_entity_id(ArtifactId),
            )


if __name__ == "__main__":
    unittest.main()
