"""Tests for the execution engine."""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.execution_engine import ExecutionEngine, Position


class TestPosition:
    def test_buy_floating_pnl_profit(self):
        pos = Position("buy", 0.1, 1.08500, spread=0.0002)
        pnl = pos.calculate_floating_pnl(1.08600)  # +10 pips
        assert pnl > 0

    def test_sell_floating_pnl_profit(self):
        pos = Position("sell", 0.1, 1.08500, spread=0.0002)
        pnl = pos.calculate_floating_pnl(1.08400)  # -10 pips (good for sell)
        assert pnl > 0

    def test_close_position(self):
        pos = Position("buy", 0.1, 1.08500, spread=0.0002)
        pos.close(1.08600)
        assert pos.status == "closed"
        assert pos.exit_price == 1.08590
        assert pos.pnl > 0

    def test_to_dict(self):
        pos = Position("buy", 0.1, 1.08500)
        d = pos.to_dict()
        assert d["direction"] == "buy"
        assert d["lot_size"] == 0.1
        assert d["status"] == "open"


class TestExecutionEngine:
    @pytest.fixture
    def engine(self):
        return ExecutionEngine(
            initial_balance=10000, spread_pips=2, commission=0
        )

    def test_open_buy(self, engine):
        pos = engine.open_position("buy", current_price=1.08500)
        assert pos is not None
        assert pos["direction"] == "buy"
        assert len(engine.open_positions) == 1

    def test_open_sell(self, engine):
        pos = engine.open_position("sell", current_price=1.08500)
        assert pos is not None
        assert pos["direction"] == "sell"

    def test_open_invalid_direction(self, engine):
        result = engine.open_position("hold", current_price=1.08500)
        assert result is None

    def test_close_position(self, engine):
        pos = engine.open_position("buy", current_price=1.08500)
        result = engine.close_position(pos["id"], 1.08600)
        assert result is not None
        assert result["status"] == "closed"
        assert len(engine.open_positions) == 0
        assert len(engine.closed_positions) == 1

    def test_close_nonexistent(self, engine):
        result = engine.close_position("fake_id", 1.08600)
        assert result is None

    def test_modify_position(self, engine):
        pos = engine.open_position("buy", current_price=1.08500)
        result = engine.modify_position(pos["id"], sl=1.08400, tp=1.08700)
        assert result is not None
        assert result["sl"] == 1.08400
        assert result["tp"] == 1.08700

    def test_check_sl_hit(self, engine):
        engine.open_position(
            "buy", current_price=1.08500, sl=1.08400, tp=1.09000
        )
        import pandas as pd
        bar = pd.Series({
            "high": 1.08550, "low": 1.08350, "close": 1.08380,
            "datetime": "2024-01-02"
        })
        closed = engine.check_sl_tp(bar)
        assert len(closed) == 1
        assert len(engine.open_positions) == 0

    def test_check_tp_hit(self, engine):
        engine.open_position(
            "buy", current_price=1.08500, sl=1.08000, tp=1.08600
        )
        import pandas as pd
        bar = pd.Series({
            "high": 1.08650, "low": 1.08480, "close": 1.08620,
            "datetime": "2024-01-02"
        })
        closed = engine.check_sl_tp(bar)
        assert len(closed) == 1

    def test_get_account_state(self, engine):
        state = engine.get_account_state(1.08500)
        assert state["balance"] == 10000
        assert state["equity"] == 10000
        assert state["total_trades"] == 0

    def test_close_all(self, engine):
        engine.open_position("buy", current_price=1.08500)
        engine.open_position("sell", current_price=1.08500)
        closed = engine.close_all_positions(1.08550)
        assert len(closed) == 2
        assert len(engine.open_positions) == 0

    def test_reset(self, engine):
        engine.open_position("buy", current_price=1.08500)
        engine.reset()
        assert engine.balance == 10000
        assert len(engine.open_positions) == 0
        assert len(engine.closed_positions) == 0

    def test_spread_is_charged_once_across_an_open_and_closed_trade(self):
        engine = ExecutionEngine(initial_balance=10000, spread_pips=2, commission=0)
        position = engine.open_position("buy", lot_size=1, current_price=1.10000)

        live = engine.get_account_state(1.10000)
        assert position["entry_price"] == 1.10010
        assert live["balance"] == 10000
        assert live["floating_pnl"] == -20
        assert live["equity"] == 9980
        assert engine.get_open_positions(1.10000)[0]["pnl"] == -20

        closed = engine.close_position(position["id"], 1.10000)
        assert closed["exit_price"] == 1.09990
        assert closed["pnl"] == -20
        assert engine.balance == 9980

    def test_commission_is_booked_once_per_side(self):
        engine = ExecutionEngine(initial_balance=10000, spread_pips=0, commission=7)
        position = engine.open_position("buy", lot_size=1, current_price=1.10000)

        live = engine.get_account_state(1.10000)
        assert live["balance"] == 9993
        assert live["floating_pnl"] == -7
        assert live["equity"] == 9986

        closed = engine.close_position(position["id"], 1.10000)
        assert closed["pnl"] == -14
        assert engine.balance == 9986

    def test_usd_base_fx_pnl_is_converted_from_quote_currency(self):
        engine = ExecutionEngine(initial_balance=10000, spread_pips=0, commission=0)
        engine.open_position("buy", lot_size=0.1, current_price=150, symbol="USDJPY")
        assert engine.get_floating_pnl(151) == 66.23

    def test_changing_balance_preserves_open_trade_pnl_and_updates_equity(self):
        engine = ExecutionEngine(initial_balance=10000, spread_pips=0, commission=0)
        engine.open_position("buy", lot_size=1, current_price=1.10000)
        before = engine.get_account_state(1.10100)

        engine.set_balance(20000)
        after = engine.get_account_state(1.10100)

        assert before["floating_pnl"] == after["floating_pnl"] == 100
        assert after["balance"] == 20000
        assert after["equity"] == 20100

    @pytest.mark.parametrize("value", [0, -10, float("inf"), float("nan"), "invalid"])
    def test_balance_must_be_positive_and_finite(self, value):
        engine = ExecutionEngine(initial_balance=10000)
        with pytest.raises(ValueError, match="positive finite"):
            engine.set_balance(value)

    def test_drawdown_includes_open_trade_equity_losses(self):
        engine = ExecutionEngine(initial_balance=10000, spread_pips=0, commission=0)
        engine.open_position("buy", lot_size=1, current_price=1.10000)
        state = engine.get_account_state(1.09000)
        assert state["equity"] == 9000
        assert state["max_drawdown"] == 10
