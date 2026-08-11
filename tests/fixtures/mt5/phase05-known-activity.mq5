#property strict

// Test-only evidence fixture. It is not a trading strategy.
const long FIXTURE_MAGIC = 50501;
int fixture_step = 0;

ENUM_ORDER_TYPE_FILLING filling_mode()
{
   long modes = 0;
   if(!SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE, modes))
      return ORDER_FILLING_FOK;
   if((modes & ORDER_FILLING_FOK) == ORDER_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_IOC;
}

bool send_market_order(const ENUM_ORDER_TYPE order_type)
{
   MqlTradeRequest request = {};
   MqlTradeResult result = {};
   request.action = TRADE_ACTION_DEAL;
   request.symbol = _Symbol;
   request.magic = FIXTURE_MAGIC;
   request.volume = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   request.type = order_type;
   request.price = SymbolInfoDouble(
      _Symbol,
      order_type == ORDER_TYPE_BUY ? SYMBOL_ASK : SYMBOL_BID
   );
   request.deviation = 100;
   request.type_filling = filling_mode();
   return OrderSend(request, result) && result.deal != 0;
}

bool close_fixture_position()
{
   if(!PositionSelect(_Symbol))
      return false;

   MqlTradeRequest request = {};
   MqlTradeResult result = {};
   ENUM_POSITION_TYPE position_type = (ENUM_POSITION_TYPE)PositionGetInteger(
      POSITION_TYPE
   );
   ENUM_ORDER_TYPE close_type = (
      position_type == POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY
   );
   request.action = TRADE_ACTION_DEAL;
   request.symbol = _Symbol;
   request.position = (ulong)PositionGetInteger(POSITION_TICKET);
   request.magic = FIXTURE_MAGIC;
   request.volume = PositionGetDouble(POSITION_VOLUME);
   request.type = close_type;
   request.price = SymbolInfoDouble(
      _Symbol,
      close_type == ORDER_TYPE_BUY ? SYMBOL_ASK : SYMBOL_BID
   );
   request.deviation = 100;
   request.type_filling = filling_mode();
   return OrderSend(request, result) && result.deal != 0;
}

void OnTick()
{
   if(fixture_step == 0 && !PositionSelect(_Symbol))
   {
      if(send_market_order(ORDER_TYPE_BUY))
         fixture_step = 1;
      return;
   }
   if(fixture_step == 1 && PositionSelect(_Symbol))
   {
      if(close_fixture_position())
      {
         fixture_step = 2;
         if(send_market_order(ORDER_TYPE_SELL))
            fixture_step = 3;
      }
      return;
   }
   if(fixture_step == 2 && !PositionSelect(_Symbol))
   {
      if(send_market_order(ORDER_TYPE_SELL))
         fixture_step = 3;
      return;
   }
   if(fixture_step == 3 && PositionSelect(_Symbol))
   {
      if(close_fixture_position())
         fixture_step = 4;
   }
}
