"""Execution engine for trade simulation."""

import uuid
import math
from datetime import datetime

import config


class Position:
    """Represents an open or closed trading position."""

    def __init__(self, direction, lot_size, entry_price, sl=None, tp=None,
                 spread=0.0, commission=0.0, entry_time=None, symbol="EURUSD",
                 contract_size=100000, quote_currency="USD"):
        self.id = str(uuid.uuid4())[:8]
        self.direction = direction  # "buy" or "sell"
        self.lot_size = lot_size
        self.entry_price = entry_price
        self.sl = sl
        self.tp = tp
        self.spread = spread
        self.commission = commission
        self.symbol = symbol
        self.contract_size = contract_size
        self.quote_currency = quote_currency
        self.entry_time = entry_time or datetime.now().isoformat()
        self.exit_price = None
        self.exit_time = None
        self.pnl = 0.0
        self.status = "open"  # "open" or "closed"

    def _exit_price(self, current_price):
        half_spread = self.spread / 2
        if self.direction == "buy":
            return current_price - half_spread
        return current_price + half_spread

    def calculate_gross_pnl(self, current_price):
        """Calculate mark-to-market P&L after spread, before commissions."""
        exit_price = self._exit_price(current_price)
        direction_sign = 1 if self.direction == "buy" else -1
        quote_pnl = (exit_price - self.entry_price) * direction_sign
        quote_pnl *= getattr(self, "contract_size", 100000) * self.lot_size

        # For USD-base FX pairs, convert quote-currency P&L back to USD.
        quote_currency = getattr(self, "quote_currency", "USD")
        symbol = getattr(self, "symbol", "EURUSD")
        if quote_currency != "USD" and symbol.startswith("USD"):
            if current_price <= 0:
                return 0.0
            quote_pnl /= current_price
        return quote_pnl

    def calculate_floating_pnl(self, current_price):
        """Net unrealized P&L, including the expected closing commission."""
        return round(self.calculate_gross_pnl(current_price) - self.commission, 2)

    def close(self, exit_price, exit_time=None):
        """Close this position.

        Args:
            exit_price: Price at which to close.
            exit_time: Time of closing.
        """
        self.exit_price = self._exit_price(exit_price)
        self.exit_time = exit_time or datetime.now().isoformat()
        gross_pnl = self.calculate_gross_pnl(exit_price)
        # Trade history reports net P&L for both entry and exit commissions.
        self.pnl = round(gross_pnl - (2 * self.commission), 2)
        self.status = "closed"

    def to_dict(self):
        """Convert position to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "direction": self.direction,
            "lot_size": self.lot_size,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "sl": self.sl,
            "tp": self.tp,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "pnl": self.pnl,
            "status": self.status,
            "spread": self.spread,
            "commission": self.commission,
            "symbol": getattr(self, "symbol", "EURUSD"),
        }


class ExecutionEngine:
    """Handles trade execution, position management, and account tracking.

    Simulates realistic trading with spreads, commissions, SL/TP,
    and full account state management.
    """

    def __init__(self, initial_balance=None, spread_pips=None,
                 commission=None):
        self.initial_balance = round(
            config.INITIAL_BALANCE if initial_balance is None else float(initial_balance), 2
        )
        if not math.isfinite(self.initial_balance) or self.initial_balance <= 0:
            raise ValueError("Balance must be a positive finite amount")
        self.balance = self.initial_balance
        self.spread_pips = config.DEFAULT_SPREAD_PIPS if spread_pips is None else float(spread_pips)
        self.commission = config.DEFAULT_COMMISSION if commission is None else float(commission)
        if not math.isfinite(self.spread_pips) or self.spread_pips < 0:
            raise ValueError("Spread must be a non-negative finite amount")
        if not math.isfinite(self.commission) or self.commission < 0:
            raise ValueError("Commission must be a non-negative finite amount")
        self.open_positions = []
        self.closed_positions = []
        self.max_balance = self.initial_balance
        self.min_balance = self.initial_balance
        self.equity_peak = self.initial_balance
        self.max_drawdown = 0.0

    def open_position(self, direction, lot_size=None, sl=None, tp=None,
                      current_price=None, current_time=None, symbol="EURUSD"):
        """Open a new trading position.

        Args:
            direction: 'buy' or 'sell'.
            lot_size: Position size in lots.
            sl: Stop loss price.
            tp: Take profit price.
            current_price: Current market price.
            current_time: Current bar datetime.

        Returns:
            Position dict if successful, None if invalid.
        """
        if direction not in ("buy", "sell"):
            return None
        try:
            current_price = float(current_price)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(current_price) or current_price <= 0:
            return None

        try:
            lot_size = config.DEFAULT_LOT_SIZE if lot_size is None else float(lot_size)
        except (TypeError, ValueError):
            return None
        spec = config.INSTRUMENT_SPECS.get(symbol)
        if spec is None or not math.isfinite(lot_size) or lot_size <= 0:
            return None

        spread_pips = getattr(self, "spread_pips", config.DEFAULT_SPREAD_PIPS)
        commission_per_lot = getattr(self, "commission", config.DEFAULT_COMMISSION)
        spread = spread_pips * spec["pip_size"]

        # Entry price includes spread for buy orders
        if direction == "buy":
            entry = current_price + spread / 2
        else:
            entry = current_price - spread / 2

        pos = Position(
            direction=direction,
            lot_size=lot_size,
            entry_price=round(entry, 5),
            sl=sl,
            tp=tp,
            spread=spread,
            commission=round(commission_per_lot * lot_size, 2),
            entry_time=str(current_time) if current_time else None,
            symbol=symbol,
            contract_size=spec["contract_size"],
            quote_currency=spec["quote_currency"],
        )

        self.open_positions.append(pos)
        self.balance = round(self.balance - pos.commission, 2)
        return pos.to_dict()

    def close_position(self, position_id, current_price, current_time=None):
        """Close a specific open position.

        Args:
            position_id: ID of the position to close.
            current_price: Current market price.
            current_time: Current datetime.

        Returns:
            Closed position dict if found, None otherwise.
        """
        for i, pos in enumerate(self.open_positions):
            if pos.id == position_id:
                pos.close(current_price, str(current_time) if current_time
                          else None)
                # Entry commission was booked when opening; book exit commission
                # and gross market P&L now, keeping balance and trade P&L in sync.
                self.balance = round(
                    self.balance + pos.calculate_gross_pnl(current_price) - pos.commission,
                    2,
                )
                self._update_balance_extremes()
                self.closed_positions.append(pos)
                self.open_positions.pop(i)
                return pos.to_dict()
        return None

    def close_all_positions(self, current_price, current_time=None):
        """Close all open positions.

        Args:
            current_price: Current market price.
            current_time: Current datetime.

        Returns:
            List of closed position dicts.
        """
        closed = []
        while self.open_positions:
            pos = self.open_positions[0]
            result = self.close_position(pos.id, current_price, current_time)
            if result:
                closed.append(result)
        return closed

    def modify_position(self, position_id, sl=None, tp=None):
        """Modify SL/TP on an open position.

        Args:
            position_id: ID of the position to modify.
            sl: New stop loss price (None to keep current).
            tp: New take profit price (None to keep current).

        Returns:
            Modified position dict if found, None otherwise.
        """
        for pos in self.open_positions:
            if pos.id == position_id:
                if sl is not None:
                    pos.sl = sl
                if tp is not None:
                    pos.tp = tp
                return pos.to_dict()
        return None

    def check_sl_tp(self, current_bar):
        """Check if any positions hit their SL or TP on the current bar.

        Args:
            current_bar: Series with high, low, close, datetime.

        Returns:
            List of positions that were closed.
        """
        closed = []
        high = current_bar["high"]
        low = current_bar["low"]
        bar_time = current_bar.get("datetime")

        positions_to_check = self.open_positions.copy()
        for pos in positions_to_check:
            close_price = None

            if pos.direction == "buy":
                if pos.sl is not None and low <= pos.sl:
                    close_price = pos.sl
                elif pos.tp is not None and high >= pos.tp:
                    close_price = pos.tp
            else:  # sell
                if pos.sl is not None and high >= pos.sl:
                    close_price = pos.sl
                elif pos.tp is not None and low <= pos.tp:
                    close_price = pos.tp

            if close_price is not None:
                result = self.close_position(pos.id, close_price, bar_time)
                if result:
                    closed.append(result)

        return closed

    def get_floating_pnl(self, current_price):
        """Calculate total floating P&L for all open positions.

        Args:
            current_price: Current market price.

        Returns:
            Total floating P&L.
        """
        total = sum(
            pos.calculate_floating_pnl(current_price)
            for pos in self.open_positions
        )
        return round(total, 2)

    def get_equity(self, current_price):
        """Calculate account equity (balance + floating P&L).

        Args:
            current_price: Current market price.

        Returns:
            Total equity value.
        """
        return round(self.balance + self.get_floating_pnl(current_price), 2)

    def get_account_state(self, current_price):
        """Get full account state snapshot.

        Args:
            current_price: Current market price.

        Returns:
            Dict with balance, equity, floating_pnl, closed_pnl,
            max_drawdown, win_rate, total_trades.
        """
        equity = self.get_equity(current_price)
        floating = self.get_floating_pnl(current_price)
        closed_pnl = sum(p.pnl for p in self.closed_positions)

        # Calculate stats
        total_trades = len(self.closed_positions)
        winners = sum(1 for p in self.closed_positions if p.pnl > 0)
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0

        # Track mark-to-market drawdown, including currently open trades.
        self.equity_peak = max(getattr(self, "equity_peak", self.initial_balance), equity)
        self.max_drawdown = getattr(self, "max_drawdown", 0.0)
        if self.equity_peak > 0:
            drawdown = (self.equity_peak - equity) / self.equity_peak * 100
            self.max_drawdown = max(self.max_drawdown, drawdown)

        return {
            "balance": round(self.balance, 2),
            "equity": equity,
            "floating_pnl": floating,
            "closed_pnl": round(closed_pnl, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "win_rate": round(win_rate, 1),
            "total_trades": total_trades,
            "open_positions": len(self.open_positions),
            "initial_balance": self.initial_balance,
        }

    def get_trade_history(self):
        """Get list of all closed trades.

        Returns:
            List of position dicts.
        """
        return [p.to_dict() for p in self.closed_positions]

    def get_open_positions(self, current_price=None):
        """Get list of all open positions.

        Returns:
            List of position dicts with current unrealized P&L when price is given.
        """
        positions = []
        for position in self.open_positions:
            item = position.to_dict()
            if current_price is not None:
                item["pnl"] = position.calculate_floating_pnl(current_price)
            positions.append(item)
        return positions

    def _update_balance_extremes(self):
        """Track peak and trough balance for drawdown calculation."""
        self.max_balance = max(self.max_balance, self.balance)
        self.min_balance = min(self.min_balance, self.balance)

    def set_balance(self, new_balance):
        """Set cash balance while preserving open trades and their mark-to-market P&L.

        The adjustment is treated as a deposit or withdrawal, not trade profit.
        Existing drawdown is preserved while its equity peak moves by the same amount.
        """
        try:
            new_balance = float(new_balance)
        except (TypeError, ValueError):
            raise ValueError("Balance must be a positive finite amount") from None
        if not math.isfinite(new_balance) or new_balance <= 0:
            raise ValueError("Balance must be a positive finite amount")
        new_balance = round(new_balance, 2)

        adjustment = new_balance - self.balance
        self.balance = new_balance
        self.initial_balance += adjustment
        self.equity_peak = max(
            0.01, getattr(self, "equity_peak", self.initial_balance) + adjustment
        )
        self.max_drawdown = getattr(self, "max_drawdown", 0.0)
        self.max_balance += adjustment
        self.min_balance += adjustment
        self._update_balance_extremes()
        return round(self.balance, 2)

    def reset(self):
        """Reset the execution engine to initial state."""
        self.balance = self.initial_balance
        self.open_positions = []
        self.closed_positions = []
        self.max_balance = self.initial_balance
        self.min_balance = self.initial_balance
        self.equity_peak = self.initial_balance
        self.max_drawdown = 0.0
