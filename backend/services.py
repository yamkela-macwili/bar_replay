"""Service layer for stateless replay operations.

Provides clean separation between HTTP routes and business logic.
All services are stateless and thread-safe.
"""

import logging
from typing import Dict, Optional, List, Any

from backend.logging_config import get_logger
from backend.engine_system import ReplaySystem, EngineFactory
from backend import data_module
import config

logger = get_logger(__name__)


class ReplayService:
    """Stateless replay control and data retrieval."""

    @staticmethod
    def load_symbol(
        session_id: str,
        symbol: str,
        timeframe: str,
        provider: str = "csv",
    ) -> Dict[str, Any]:
        """Initialize replay engines for a symbol.

        Args:
            session_id: Session UUID
            symbol: Trading symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "H1")
            provider: Data provider ("csv", "yfinance", "mt5")

        Returns:
            Dict with initialization result

        Raises:
            ValueError: If data cannot be loaded
        """
        try:
            system = EngineFactory.create(
                symbol=symbol,
                timeframe=timeframe,
                provider=provider,
                session_id=session_id,
            )
            logger.info(
                f"Loaded {symbol} {timeframe} "
                f"({system.replay_engine.total_bars} bars)"
            )
            return {
                "status": "ok",
                "symbol": symbol,
                "timeframe": timeframe,
                "total_bars": system.replay_engine.total_bars,
                "start_index": system.replay_engine.current_index,
                "visible_count": config.INITIAL_BAR_COUNT,
                "session_id": system.session_id,
            }
        except Exception as e:
            logger.error(f"Failed to load {symbol}: {e}", exc_info=True)
            raise ValueError(f"Cannot load {symbol} {timeframe}: {e}") from e

    @staticmethod
    def get_visible_data(system: ReplaySystem) -> Dict[str, Any]:
        """Get visible chart bars and indicator values.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with OHLCV bars and indicators
        """
        visible = system.replay_engine.get_visible_data(
            max_bars=config.INITIAL_BAR_COUNT
        )
        bars = visible["bars"]
        indicators_data = visible["indicators"]

        if system.execution_engine and len(system.execution_engine.open_positions) > 0:
            current_bar = system.replay_engine.get_current_bar()
            system.execution_engine.check_sl_tp(current_bar)

        current_price = float(bars.iloc[-1]["close"]) if len(bars) > 0 else 0.0

        return {
            "bars": {
                "datetime": bars["datetime"].astype(str).tolist(),
                "open": bars["open"].tolist(),
                "high": bars["high"].tolist(),
                "low": bars["low"].tolist(),
                "close": bars["close"].tolist(),
                "volume": bars["volume"].tolist(),
            },
            "indicators": indicators_data,
            "progress": system.replay_engine.get_progress(),
            "account": system.execution_engine.get_account_state(current_price),
            "open_positions": system.execution_engine.get_open_positions(),
            "trade_history": system.execution_engine.get_trade_history(),
            "session_id": system.session_id,
        }

    @staticmethod
    def step_forward(system: ReplaySystem) -> Dict[str, Any]:
        """Step replay forward by one bar.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with progress state
        """
        success = system.replay_engine.step_forward()

        if success and system.execution_engine:
            current_bar = system.replay_engine.get_current_bar()
            system.execution_engine.check_sl_tp(current_bar)

        return {
            "status": "ok" if success else "end",
            "progress": system.replay_engine.get_progress(),
        }

    @staticmethod
    def step_back(system: ReplaySystem) -> Dict[str, Any]:
        """Step replay backward by one bar.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with progress state
        """
        success = system.replay_engine.step_back()
        return {
            "status": "ok" if success else "start",
            "progress": system.replay_engine.get_progress(),
        }

    @staticmethod
    def set_speed(system: ReplaySystem, speed: int) -> Dict[str, Any]:
        """Set replay speed.

        Args:
            system: ReplaySystem instance
            speed: Speed multiplier (1, 2, 5, 10)

        Returns:
            Dict with speed confirmation
        """
        success = system.replay_engine.set_speed(speed)
        return {
            "status": "ok" if success else "error",
            "speed": system.replay_engine.speed,
            "interval_ms": system.replay_engine.get_interval_ms()
            if success
            else None,
        }

    @staticmethod
    def play(system: ReplaySystem) -> Dict[str, Any]:
        """Start auto-play.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with play state
        """
        system.replay_engine.play()
        return {
            "status": "ok",
            "interval_ms": system.replay_engine.get_interval_ms(),
            "progress": system.replay_engine.get_progress(),
        }

    @staticmethod
    def pause(system: ReplaySystem) -> Dict[str, Any]:
        """Pause auto-play.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with pause state
        """
        system.replay_engine.pause()
        return {
            "status": "ok",
            "progress": system.replay_engine.get_progress(),
        }

    @staticmethod
    def jump(system: ReplaySystem, index: Optional[int] = None, date: Optional[str] = None) -> Dict[str, Any]:
        """Jump to bar index or date.

        Args:
            system: ReplaySystem instance
            index: Bar index to jump to
            date: Date string to jump to

        Returns:
            Dict with jump result
        """
        success = False
        if index is not None:
            success = system.replay_engine.jump_to(int(index))
        elif date:
            success = system.replay_engine.jump_to_date(date)

        return {
            "status": "ok" if success else "error",
            "progress": system.replay_engine.get_progress(),
        }

    @staticmethod
    def load_more_bars(system: ReplaySystem, direction: str = "backward") -> Dict[str, Any]:
        """Fetch additional bars for lazy loading.

        Args:
            system: ReplaySystem instance
            direction: "backward" or "forward"

        Returns:
            Dict with bars added count
        """
        try:
            provider = data_module.get_provider(system.provider)

            if direction == "backward":
                anchor_time = system.replay_engine.data["datetime"].min().isoformat()
                new_data = provider.fetch_bars(
                    system.symbol,
                    system.timeframe,
                    count=config.LAZY_LOAD_COUNT,
                    before=anchor_time,
                )
                num_added = system.replay_engine.prepend_data(new_data)
            else:
                num_added = 0

            if num_added > 0:
                system.refresh_indicators()

            return {
                "status": "ok",
                "added": num_added,
                "direction": direction,
                "total_bars": system.replay_engine.total_bars,
                "current_index": system.replay_engine.current_index,
                "session_id": system.session_id,
            }
        except Exception as e:
            logger.error(f"Failed to load more bars: {e}", exc_info=True)
            raise


class TradeService:
    """Stateless trade execution operations."""

    @staticmethod
    def open_position(
        system: ReplaySystem,
        direction: str,
        lot_size: float = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Open a trading position.

        Args:
            system: ReplaySystem instance
            direction: "buy" or "sell"
            lot_size: Position size
            sl: Stop loss price
            tp: Take profit price

        Returns:
            Dict with position and account state
        """
        current_bar = system.replay_engine.get_current_bar()
        current_price = float(current_bar["close"])
        current_time = current_bar["datetime"]

        result = system.execution_engine.open_position(
            direction=direction,
            lot_size=float(lot_size or config.DEFAULT_LOT_SIZE),
            sl=sl,
            tp=tp,
            current_price=current_price,
            current_time=current_time,
        )

        return {
            "status": "ok" if result else "error",
            "position": result,
            "account": system.execution_engine.get_account_state(current_price),
        }

    @staticmethod
    def close_position(
        system: ReplaySystem,
        position_id: str,
    ) -> Dict[str, Any]:
        """Close a trading position.

        Args:
            system: ReplaySystem instance
            position_id: ID of position to close

        Returns:
            Dict with closed position and account state
        """
        current_bar = system.replay_engine.get_current_bar()
        current_price = float(current_bar["close"])
        current_time = current_bar["datetime"]

        result = system.execution_engine.close_position(
            position_id, current_price, current_time
        )

        return {
            "status": "ok" if result else "error",
            "position": result,
            "account": system.execution_engine.get_account_state(current_price),
        }

    @staticmethod
    def close_all_positions(system: ReplaySystem) -> Dict[str, Any]:
        """Close all open positions.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with closed positions and account state
        """
        current_bar = system.replay_engine.get_current_bar()
        current_price = float(current_bar["close"])
        current_time = current_bar["datetime"]

        results = system.execution_engine.close_all_positions(
            current_price, current_time
        )

        return {
            "status": "ok",
            "closed": results,
            "account": system.execution_engine.get_account_state(current_price),
        }

    @staticmethod
    def modify_position(
        system: ReplaySystem,
        position_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Modify position SL/TP.

        Args:
            system: ReplaySystem instance
            position_id: Position ID
            sl: New stop loss
            tp: New take profit

        Returns:
            Dict with modified position
        """
        result = system.execution_engine.modify_position(
            position_id, sl=sl, tp=tp
        )
        return {
            "status": "ok" if result else "error",
            "position": result,
        }


class IndicatorService:
    """Stateless indicator management."""

    @staticmethod
    def toggle_indicator(
        system: ReplaySystem,
        name: str,
        settings: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Toggle indicator on/off.

        Args:
            system: ReplaySystem instance
            name: Indicator name
            settings: Indicator settings dict

        Returns:
            Dict with updated indicators
        """
        if name in system.active_indicators:
            del system.active_indicators[name]
        else:
            system.active_indicators[name] = settings or {}

        system.refresh_indicators()

        return {
            "status": "ok",
            "active_indicators": system.active_indicators,
        }

    @staticmethod
    def set_indicator(
        system: ReplaySystem,
        name: str,
        settings: Dict,
    ) -> Dict[str, Any]:
        """Set indicator settings.

        Args:
            system: ReplaySystem instance
            name: Indicator name
            settings: Indicator settings

        Returns:
            Dict with updated indicators
        """
        system.active_indicators[name] = settings
        system.refresh_indicators()

        return {
            "status": "ok",
            "active_indicators": system.active_indicators,
        }

    @staticmethod
    def remove_indicator(
        system: ReplaySystem,
        name: str,
    ) -> Dict[str, Any]:
        """Remove indicator.

        Args:
            system: ReplaySystem instance
            name: Indicator name

        Returns:
            Dict with updated indicators
        """
        system.active_indicators.pop(name, None)
        system.refresh_indicators()

        return {
            "status": "ok",
            "active_indicators": system.active_indicators,
        }

    @staticmethod
    def clear_indicators(system: ReplaySystem) -> Dict[str, Any]:
        """Clear all indicators.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with cleared indicators
        """
        system.active_indicators = {}
        system.refresh_indicators()

        return {
            "status": "ok",
            "active_indicators": system.active_indicators,
        }


class DataService:
    """Stateless data retrieval operations."""

    @staticmethod
    def get_available_symbols(provider: str = "csv") -> List[tuple]:
        """Get available symbols for provider.

        Args:
            provider: Data provider name

        Returns:
            List of (symbol, timeframe) tuples
        """
        try:
            prov = data_module.get_provider(provider)
            return prov.get_available_symbols()
        except Exception as e:
            logger.warning(f"Failed to get symbols for {provider}: {e}")
            return []

    @staticmethod
    def get_account_stats(system: ReplaySystem) -> Dict[str, Any]:
        """Get account statistics.

        Args:
            system: ReplaySystem instance

        Returns:
            Dict with account stats
        """
        current_price = float(system.replay_engine.get_current_bar()["close"])

        return {
            "status": "ok",
            "account": system.execution_engine.get_account_state(current_price),
            "open_positions": system.execution_engine.get_open_positions(),
            "trade_history": system.execution_engine.get_trade_history(),
        }
