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
        assert pos.exit_price == 1.08600
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
