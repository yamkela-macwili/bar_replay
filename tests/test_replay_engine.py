"""Tests for the replay engine."""

import os
import sys
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.replay_engine import ReplayEngine
from backend.data_module import load_symbol


@pytest.fixture
def engine():
    df = load_symbol("EURUSD", "H1")
    return ReplayEngine(df)


class TestReplayEngine:
    def test_initial_state(self, engine):
        assert engine.current_index == 0
        assert engine.state == "paused"
        assert engine.speed == 1
        assert engine.total_bars == 500

    def test_step_forward(self, engine):
        assert engine.step_forward() is True
        assert engine.current_index == 1

    def test_step_back_at_start(self, engine):
        assert engine.step_back() is False
        assert engine.current_index == 0

    def test_step_back(self, engine):
        engine.step_forward()
        engine.step_forward()
        assert engine.step_back() is True
        assert engine.current_index == 1

    def test_step_forward_at_end(self, engine):
        engine.current_index = engine.total_bars - 1
        assert engine.step_forward() is False

    def test_play_pause(self, engine):
        engine.play()
        assert engine.is_playing() is True
        engine.pause()
        assert engine.is_playing() is False

    def test_jump_to_valid(self, engine):
        assert engine.jump_to(50) is True
        assert engine.current_index == 50

    def test_jump_to_invalid(self, engine):
        assert engine.jump_to(-1) is False
        assert engine.jump_to(99999) is False

    def test_set_speed(self, engine):
        assert engine.set_speed(5) is True
        assert engine.speed == 5
        assert engine.set_speed(3) is False  # invalid

    def test_get_visible_data(self, engine):
        engine.jump_to(10)
        visible = engine.get_visible_data()
        assert len(visible["bars"]) == 11  # bars 0-10

    def test_get_current_bar(self, engine):
        bar = engine.get_current_bar()
        assert "open" in bar.index
        assert "close" in bar.index

    def test_get_progress(self, engine):
        progress = engine.get_progress()
        assert progress["current_index"] == 0
        assert progress["total_bars"] == 500
        assert progress["state"] == "paused"

    def test_interval_ms(self, engine):
        assert engine.get_interval_ms() == 1000
        engine.set_speed(5)
        assert engine.get_interval_ms() == 200
