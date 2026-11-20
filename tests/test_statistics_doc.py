"""docs/statistics.md must state the numbers the implementation actually uses."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import stats

DOC = Path(__file__).resolve().parent.parent / "docs" / "statistics.md"


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_document_exists(doc: str):
    assert doc.strip()


def test_the_documented_minimum_detectable_effect_is_the_default(doc: str):
    effect = stats.MINIMUM_DETECTABLE_EFFECT
    assert f"**{effect * 100:.0f} percentage points of win rate" in doc
    assert f"at {stats.DEFAULT_POWER:.0%} power" in doc
    assert f"alpha = {stats.DEFAULT_ALPHA}" in doc


def test_the_documented_sample_sizes_are_the_computed_ones(doc: str):
    for delta in (0.05, 0.03, 0.02):
        assert f"| {stats.sample_size_per_arm(delta):,} |" in doc
        assert f"**{stats.sample_size_total(delta):,}**" in doc
        assert f"| {stats.sample_size_total(delta, power=0.95):,} |" in doc

    assert f"{stats.sample_size_total(stats.CONFIRMATION_EFFECT):,} games" in doc
    assert f"**{stats.sample_size_total(stats.MINIMUM_DETECTABLE_EFFECT):,}**" in doc
    per_arm_low_rate = stats.sample_size_per_arm(
        0.03, baseline_rate=0.30, candidate_rate=0.30
    )
    assert f"{per_arm_low_rate:,} games per arm" in doc


def test_the_documented_quantiles_are_the_computed_ones(doc: str):
    assert f"z_{{0.975}} = {stats.z_for_confidence(0.95):.6f}" in doc
    assert f"z_{{0.80}} = {stats.z_for_power(0.80):.6f}" in doc
    assert f"z_{{0.95}} = {stats.z_for_power(0.95):.6f}" in doc
    k80 = (stats.z_for_confidence(0.95) + stats.z_for_power(0.80)) ** 2
    k95 = (stats.z_for_confidence(0.95) + stats.z_for_power(0.95)) ** 2
    assert f"`{k80:.5f}`" in doc
    assert f"`{k95:.5f}`" in doc


def test_the_documented_sprt_design_is_the_default_design(doc: str):
    design = stats.SprtDesign()
    assert f"p0 = {design.p0:.2f}" in doc
    assert f"p1 = {design.p1:.2f}" in doc
    assert f"+{stats.SCREENING_MARGIN * 100:.0f} percentage points" in doc
    assert f"alpha = {design.alpha}, beta = {design.beta}" in doc
    assert f"| {design.game_cap:,} |" in doc
    assert f"{design.game_cap:,} games means" in doc
    assert f"{design.accept_threshold:+.5f}" in doc
    assert f"{design.reject_threshold:+.5f}" in doc
    assert f"{design.llr_win:+.5f}" in doc
    assert f"{design.llr_loss:+.5f}" in doc


def test_the_documented_per_matchup_threshold_is_the_default(doc: str):
    required = stats.sample_size_total(stats.MINIMUM_DETECTABLE_EFFECT)
    assert f"below {required:,} is marked diagnostic-only" in doc
    assert f"{required:,} games in that matchup" in doc


def test_the_documented_record_shape_matches_the_module_contract(doc: str):
    for field in ("`opponent`", "`seed`", "`won`"):
        assert field in doc
    opponent, seed = stats.DEFAULT_PAIR_ON
    assert f'`("{opponent}", "{seed}")`' in doc


def test_the_documented_identity_fields_are_the_implemented_ones(doc: str):
    assert f"all {len(stats.IDENTITY_FIELDS)} identity fields" in doc


def test_the_documented_number_of_alternative_weightings_is_the_enforced_one(doc: str):
    assert "**two** alternative" in doc
