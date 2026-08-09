import json
import unittest
from dataclasses import FrozenInstanceError

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.errors import (
    EvidenceInvariantError,
    InvalidIdentifierError,
    InvalidValueError,
    ProvenanceInvariantError,
)
from ea_research_lab.domain.identifiers import RequestId, RunId


class RequestContextTests(unittest.TestCase):
    def test_context_is_transport_neutral_and_frozen(self) -> None:
        context = RequestContext(
            request_id=new_entity_id(RequestId),
            caller_id="researcher-1",
        )

        with self.assertRaises(FrozenInstanceError):
            context.caller_id = "other"
        with self.assertRaises(InvalidValueError):
            RequestContext(new_entity_id(RequestId), " ")
        with self.assertRaises(InvalidValueError):
            RequestContext(new_entity_id(RunId))


class ErrorContractTests(unittest.TestCase):
    def test_domain_error_codes_are_stable(self) -> None:
        expected = {
            InvalidIdentifierError: "invalid_identifier",
            InvalidValueError: "invalid_value",
            ProvenanceInvariantError: "invalid_provenance",
            EvidenceInvariantError: "invalid_evidence_manifest",
        }

        for error_type, code in expected.items():
            with self.subTest(error_type=error_type.__name__):
                self.assertEqual(error_type.code, code)

    def test_application_error_serialization_is_safe(self) -> None:
        request_id = new_entity_id(RequestId)
        error = ApplicationError(
            code=ApplicationErrorCode.INVALID_VALUE,
            message="The supplied value is invalid.",
            details={"field": "schema_version", "allowed": ["0.1.0"]},
            request_id=request_id,
            cause=RuntimeError("internal detail"),
        )

        serialized = error.to_dict()
        self.assertEqual(serialized["request_id"], str(request_id))
        self.assertNotIn("cause", serialized)
        self.assertNotIn("internal detail", json.dumps(serialized))
        json.dumps(serialized, allow_nan=False)

    def test_application_error_rejects_unsafe_details(self) -> None:
        with self.assertRaises(TypeError):
            ApplicationError(
                ApplicationErrorCode.INVALID_VALUE,
                "Invalid value.",
                details={"unsafe": object()},
            )
        with self.assertRaises(TypeError):
            ApplicationError(
                ApplicationErrorCode.INVALID_VALUE,
                "Invalid value.",
                details={"number": float("nan")},
            )


if __name__ == "__main__":
    unittest.main()
