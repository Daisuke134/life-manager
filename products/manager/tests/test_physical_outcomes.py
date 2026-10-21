"""D005–D007 offline preparation. Every record is fictional, public fixture data."""
import importlib
import importlib.util
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from manager_core.models.source import Source


START = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
CHANNELS = {
    "indoor_pm25": ("ug/m3", 0, 1000),
    "outdoor_pm25": ("ug/m3", 0, 1000),
    "indoor_temperature": ("degC", -20, 60),
    "outdoor_temperature": ("degC", -20, 60),
    "indoor_relative_humidity": ("%", 0, 100),
    "outdoor_relative_humidity": ("%", 0, 100),
    "power": ("W", 0, 10000),
    "noise": ("dBA", 0, 150),
}


def physical():
    assert importlib.util.find_spec("manager_core.physical_outcomes") is not None, "physical-session implementation missing"
    return importlib.import_module("manager_core.physical_outcomes")


def source(name, at=START - timedelta(days=1)):
    return Source(name, "https://example.org/" + name, "CC0-1.0", "allowed_with_conditions",
                  sha256(name.encode()).hexdigest(), at, "public_nonpersonal")


def design():
    return physical().PhysicalSessionDesign(
        "session-1", "treated-room", "control-room", "purifier-1", "manager-executor",
        START, START + timedelta(hours=1), START + timedelta(hours=2), 30,
        source("prospective-protocol"),
    )


def reading(zone, channel, at, value, *, suffix=""):
    m = physical()
    unit, lower, upper = CHANNELS[channel]
    instrument = zone + "-" + (channel if channel in ("power", "noise") else "environment")
    identifier = f"{zone}-{channel}-{int(at.timestamp())}{suffix}"
    calibration = m.Calibration(instrument, channel, unit, lower, upper, START - timedelta(days=1),
                                START + timedelta(days=1), source(instrument + "-" + channel + "-calibration"))
    return m.PhysicalReading(identifier, "session-1", zone, instrument, channel, at, value, unit,
                             source(identifier, at + timedelta(minutes=1)), calibration,
                             "sensor_missing" if value is None else None)


def complete_readings():
    readings = []
    for zone, minutes, pm in (("treated-room", 10, 20), ("control-room", 10, 12),
                              ("treated-room", 70, 10), ("control-room", 70, 8)):
        values = {"indoor_pm25": pm, "outdoor_pm25": 18, "indoor_temperature": 22,
                  "outdoor_temperature": 19, "indoor_relative_humidity": 50,
                  "outdoor_relative_humidity": 60, "power": 35, "noise": 42}
        readings.extend(reading(zone, channel, START + timedelta(minutes=minutes), value)
                        for channel, value in values.items())
    return tuple(readings)


def analyze(readings=None, **kwargs):
    return physical().analyze_physical_session(design(), complete_readings() if readings is None else readings, **kwargs)


class PhysicalOutcomeTests(unittest.TestCase):
    def test_synchronized_treated_control_comparison_is_descriptive_only(self):
        result = analyze()
        self.assertEqual(len(result.frames), 4)
        self.assertEqual(len(result.pairs), 2)
        self.assertEqual(result.comparison.before_gap, 8)
        self.assertEqual(result.comparison.after_gap, 2)
        self.assertEqual(result.comparison.change_in_gap, -6)
        self.assertEqual(result.comparison.unit, "ug/m3")
        self.assertIsNone(result.comparison.causal_effect)
        self.assertIsNone(result.comparison.confidence_interval)
        self.assertEqual(result.proof_level, "P0")
        self.assertEqual(result.measurement_authentication, "NOT_VERIFIED")
        self.assertEqual(result.health_outcome_status, "NOT_MEASURED")
        self.assertEqual(result.action, "NO_ACTION")

    def test_bad_missing_and_out_of_calibration_rows_are_retained_with_provenance(self):
        rows = list(complete_readings())
        rows[1] = replace(rows[1], value=None, missing_reason="provider_missing")
        rows[2] = replace(rows[2], value=float("nan"))
        rows[3] = replace(rows[3], value=80)
        result = analyze(tuple(rows))
        rejected = {item.reading.observation_id: item for item in result.excluded}
        self.assertEqual(rejected[rows[1].observation_id].reason, "MISSING_VALUE")
        self.assertEqual(rejected[rows[2].observation_id].reason, "INVALID_VALUE")
        self.assertEqual(rejected[rows[3].observation_id].reason, "OUT_OF_CALIBRATION_RANGE")
        self.assertEqual(rejected[rows[1].observation_id].reading.source, rows[1].source)
        self.assertEqual(result.readings, tuple(rows))
        self.assertIsNone(result.comparison.change_in_gap)

    def test_units_calibration_binding_and_expiry_are_not_guessed(self):
        original = complete_readings()
        variants = (
            (replace(original[0], unit="mg/m3"), "UNIT_MISMATCH"),
            (replace(original[0], calibration=None), "CALIBRATION_MISSING"),
            (replace(original[0], calibration=replace(original[0].calibration, instrument_id="other")), "CALIBRATION_MISMATCH"),
            (replace(original[0], calibration=replace(original[0].calibration, valid_until=START)), "CALIBRATION_EXPIRED"),
            (replace(original[0], value=True), "INVALID_VALUE"),
            (replace(original[0], value=-1), "OUTSIDE_PHYSICAL_RANGE"),
        )
        for changed, expected in variants:
            with self.subTest(expected=expected):
                result = analyze((changed,) + original[1:])
                self.assertEqual(result.excluded[0].reason, expected)
                self.assertIsNone(result.comparison.change_in_gap)

    def test_asynchronous_or_ambiguous_covariates_do_not_make_complete_frames(self):
        rows = list(complete_readings())
        rows[1] = replace(rows[1], recorded_at=rows[1].recorded_at + timedelta(seconds=31))
        result = analyze(tuple(rows))
        frame = next(frame for frame in result.frames if frame.zone_id == "treated-room" and frame.period == "before")
        self.assertIn("outdoor_pm25", frame.missing_channels)
        self.assertIsNone(result.comparison.change_in_gap)
        rows = complete_readings()
        duplicated = replace(rows[1], observation_id="second-outdoor-row",
                             source=source("second-outdoor-row", rows[1].recorded_at + timedelta(minutes=1)))
        result = analyze(rows + (duplicated,))
        self.assertIsNone(result.comparison.change_in_gap)

    def test_historical_control_is_not_contemporaneous_and_cannot_supply_effect(self):
        rows = tuple(replace(row, recorded_at=row.recorded_at + timedelta(minutes=5),
                             source=replace(row.source, retrieved_at=row.source.retrieved_at + timedelta(minutes=5)))
                     if row.zone_id == "control-room" else row for row in complete_readings())
        result = analyze(rows)
        self.assertEqual(len(result.pairs), 0)
        self.assertIsNone(result.comparison.before_gap)
        self.assertIsNone(result.comparison.change_in_gap)
        self.assertEqual(result.comparison.status, "INCOMPLETE_CONTEMPORANEOUS_COMPARISON")

    def test_control_reading_cannot_be_reused_to_inflate_comparison_count(self):
        rows = complete_readings()
        extras = tuple(replace(row, observation_id=row.observation_id + "-repeat",
                               recorded_at=row.recorded_at + timedelta(seconds=10))
                       for row in rows if row.zone_id == "treated-room" and row.recorded_at < START + timedelta(hours=1))
        result = analyze(rows + extras)
        self.assertIsNone(result.comparison.before_gap)

    def test_unknown_power_noise_and_cost_stay_unknown(self):
        rows = tuple(row for row in complete_readings() if row.channel not in ("power", "noise"))
        result = analyze(rows)
        self.assertEqual(result.comparison.change_in_gap, -6)
        self.assertTrue(all(item.count == 0 and item.minimum is None and item.maximum is None for item in result.meters))
        self.assertEqual(result.harm_measurement_status, "INCOMPLETE")
        self.assertIsNone(result.cost_minor)
        self.assertIsNone(result.net_benefit)

    def test_actuator_self_reading_is_not_an_independent_meter(self):
        rows = list(complete_readings())
        index = next(i for i, row in enumerate(rows) if row.channel == "power")
        rows[index] = replace(rows[index], instrument_id="purifier-1",
                              calibration=replace(rows[index].calibration, instrument_id="purifier-1"))
        result = analyze(tuple(rows))
        self.assertEqual(result.excluded[0].reason, "ACTUATOR_SELF_READING")
        self.assertEqual(result.harm_measurement_status, "INCOMPLETE")
        rows = list(complete_readings())
        rows[index] = replace(rows[index], source=source("manager-executor", rows[index].recorded_at + timedelta(minutes=1)))
        self.assertEqual(analyze(tuple(rows)).excluded[0].reason, "EXECUTOR_ONLY_READING")

    def test_meter_units_cost_currency_and_noise_summary_remain_separate(self):
        result = analyze(cost_minor=120, currency="JPY", cost_source=source("metered-cost"))
        self.assertEqual(result.cost_minor, 120)
        self.assertEqual(result.currency, "JPY")
        self.assertEqual({item.unit for item in result.meters}, {"W", "dBA"})
        self.assertTrue(all(item.mean is None for item in result.meters if item.channel == "noise"))
        self.assertTrue(all(item.mean == 35 for item in result.meters if item.channel == "power"))
        self.assertIsNone(result.energy_kwh)
        self.assertIsNone(result.net_benefit)
        self.assertEqual(result.harm_measurement_status, "DECLARED_MEASUREMENTS_ONLY")
        with self.assertRaises(ValueError):
            analyze(cost_minor=120, currency="JPY")

    def test_duplicate_ids_unbound_session_and_future_protocol_fail_closed(self):
        rows = complete_readings()
        with self.assertRaises(ValueError):
            analyze(rows + (rows[0],))
        with self.assertRaises(ValueError):
            replace(design(), protocol=source("late-protocol", START + timedelta(minutes=1)))
        with self.assertRaises(ValueError):
            replace(design(), control_zone="treated-room")
        result = analyze((replace(rows[0], session_id="other-session"),) + rows[1:])
        self.assertEqual(result.excluded[0].reason, "SESSION_MISMATCH")
        self.assertIsNone(result.comparison.change_in_gap)

    def test_declared_provenance_hash_is_checked_without_authenticating_the_measurements(self):
        rows = complete_readings()
        with self.assertRaises(ValueError):
            analyze(rows, snapshots={rows[0].source.source_id: b"changed"})
        result = analyze(rows, snapshots={rows[0].source.source_id: rows[0].source.source_id.encode()})
        self.assertEqual(result.measurement_authentication, "NOT_VERIFIED")
        self.assertEqual(result.proof_level, "P0")
        self.assertIn(rows[0].source, result.sources)


if __name__ == "__main__":
    unittest.main()
