"""Replay engine for bar-by-bar market simulation."""


class ReplayEngine:
    """Core replay engine that manages bar-by-bar playback of market data.

    Supports play, pause, step forward/back, jump to position, and
    adjustable speed. Tracks state history for reverse replay.
    """

    VALID_SPEEDS = [1, 2, 5, 10]

    def __init__(self, data):
        """Initialize the replay engine.

        Args:
            data: DataFrame with OHLCV data (datetime, open, high, low,
                  close, volume).
        """
        self.data = data.copy()
        self.total_bars = len(data)
        self.current_index = 0
        self.speed = 1
        self.state = "paused"

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
        import pandas as pd
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

    def get_visible_data(self, max_bars=200):
        """Get bars visible on the chart (from start to current index).

        Args:
            max_bars: Maximum number of bars to return (most recent).

        Returns:
            DataFrame slice of visible bars.
        """
        end = self.current_index + 1
        start = max(0, end - max_bars)
        return self.data.iloc[start:end].copy()

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
