"""Replay engine for bar-by-bar market simulation."""

import pandas as pd


class ReplayEngine:
    """Core replay engine that manages bar-by-bar playback of market data.

    Supports play, pause, step forward/back, jump to position, and
    adjustable speed. Tracks state history for reverse replay.
    """

    VALID_SPEEDS = [1, 2, 5, 10]

    def __init__(self, data, start_index=None):
        """Initialize the replay engine.

        Args:
            data: DataFrame with OHLCV data (datetime, open, high, low,
                  close, volume).
            start_index: Optional initial index (defaults to 0).
        """
        import config
        self.data = data.copy()
        self.total_bars = len(data)
        self.max_bars_limit = getattr(config, "MAX_BARS_LIMIT", 3000)
        
        if start_index is None:
            self.current_index = 0
        else:
            self.current_index = min(max(0, start_index), self.total_bars - 1)
            
        self.speed = 1
        self.state = "paused"
        self.indicators = {} # Stores full-history indicators

    def step_forward(self):
        """Advance replay by one bar.

        Returns:
            True if step was successful, False if at end.
        """
        if self.current_index < self.total_bars - 1:
            self.current_index += 1
            return True
        return False

    def step_back(self):
        """Rewind replay by one bar.

        Returns:
            True if step was successful, False if at beginning.
        """
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False

    def play(self):
        """Set replay state to playing."""
        self.state = "playing"

    def pause(self):
        """Set replay state to paused."""
        self.state = "paused"

    def is_playing(self):
        """Check if replay is currently playing.

        Returns:
            True if state is 'playing'.
        """
        return self.state == "playing"

    def jump_to(self, index):
        """Jump to a specific bar index.

        Args:
            index: Bar index to jump to (0-based).

        Returns:
            True if jump was successful, False if index out of range.
        """
        if 0 <= index < self.total_bars:
            self.current_index = index
            return True
        return False

    def jump_to_date(self, date_str):
        """Jump to the nearest bar at or after a specific date.

        Args:
            date_str: Date string to search for.

        Returns:
            True if a matching bar was found, False otherwise.
        """
        target = pd.to_datetime(date_str)
        mask = self.data["datetime"] >= target
        if mask.any():
            self.current_index = mask.idxmax()
            return True
        return False

    def set_speed(self, speed):
        """Set the replay speed multiplier.

        Args:
            speed: Speed multiplier (1, 2, 5, or 10).

        Returns:
            True if speed is valid, False otherwise.
        """
        if speed in self.VALID_SPEEDS:
            self.speed = speed
            return True
        return False

    def set_indicators(self, indicator_data):
        """Store full-history indicator data.

        Args:
            indicator_data: Dict mapping indicator names to Series/Lists.
        """
        self.indicators = indicator_data

    def replay_from(self, index):
        """Reset state and start replaying from a specific index.
        
        Ensures deterministic results for backtesting.
        """
        self.pause()
        self.current_index = min(max(0, index), self.total_bars - 1)
        # In a real backtest, this would also trigger ExecutionEngine.reset()
        return True

    def get_visible_data(self, max_bars=200):
        """Get bars visible on the chart (from start to current index).

        Args:
            max_bars: Maximum number of bars to return (most recent).

        Returns:
            Dict with bars and indicators slices.
        """
        end = self.current_index + 1
        start = max(0, end - max_bars)
        
        bars_slice = self.data.iloc[start:end].copy()
        indicators_slice = {}
        for name, values in self.indicators.items():
            if isinstance(values, pd.Series):
                indicators_slice[name] = values.iloc[start:end].tolist()
            else:
                indicators_slice[name] = values[start:end]
                
        return {
            "bars": bars_slice,
            "indicators": indicators_slice
        }

    def get_current_bar(self):
        """Get the current bar data.

        Returns:
            Series with current bar OHLCV data.
        """
        return self.data.iloc[self.current_index]

    def get_progress(self):
        """Get replay progress info.

        Returns:
            Dict with current_index, total_bars, percentage, state, speed.
        """
        pct = (self.current_index / max(1, self.total_bars - 1)) * 100
        return {
            "current_index": self.current_index,
            "total_bars": self.total_bars,
            "percentage": round(pct, 1),
            "state": self.state,
            "speed": self.speed,
            "current_datetime": str(
                self.data.iloc[self.current_index]["datetime"]
            )
        }

    def get_interval_ms(self):
        """Get the auto-play interval in milliseconds based on speed.

        Returns:
            Interval in milliseconds.
        """
        base_interval = 1000  # 1 second per bar at 1x
        return base_interval // self.speed

    def prepend_data(self, new_data):
        """Prepend new (older) historical data to the engine.

        Used for lazy loading bars as the user scrolls back.

        Args:
            new_data: DataFrame with older OHLCV data.

        Returns:
            Number of new bars added.
        """
        if new_data.empty:
            return 0

        # Memory Ceiling Protection: Lock backward scrolling
        if len(self.data) >= self.max_bars_limit:
            print(f"ℹ️ Memory ceiling reached ({self.max_bars_limit} bars). Locking backward scrolling.")
            return 0

        # Filter out any bars that might already exist (overlap)
        existing_start = self.data["datetime"].min()
        new_data = new_data[new_data["datetime"] < existing_start]

        if new_data.empty:
            return 0

        # Ensure we don't exceed limit with new data
        if len(self.data) + len(new_data) > self.max_bars_limit:
            allowed_count = self.max_bars_limit - len(self.data)
            new_data = new_data.tail(allowed_count)
            print(f"ℹ️ Prepend limited to {allowed_count} bars to respect ceiling.")

        num_new_bars = len(new_data)
        if num_new_bars == 0:
            return 0
            
        # Merge data
        self.data = pd.concat([new_data, self.data]).reset_index(drop=True)
        
        self.total_bars = len(self.data)
        self.current_index += num_new_bars
        
        # Note: Indicators must be recomputed by the caller using full history
        return num_new_bars
