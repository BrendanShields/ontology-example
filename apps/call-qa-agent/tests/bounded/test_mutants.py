"""Each planted fault must be reported by the property named for it, and by nothing cruder."""

from __future__ import annotations

import pytest

from . import explore
from .mutants import MUTANTS, copy_package, explore_copy, plant

pytestmark = pytest.mark.mutants


def test_an_untouched_copy_holds(tmp_path):
    copied = copy_package(tmp_path)
    explored = explore_copy(tmp_path)
    assert explored.package.parent == copied
    assert (explored.violated, explored.returncode) == (None, 0), explored.output


@pytest.mark.parametrize("mutant", MUTANTS, ids=lambda mutant: mutant.name)
def test_mutant_is_reported_by_its_property(mutant, tmp_path):
    copied = copy_package(tmp_path)
    plant(mutant, copied)
    explored = explore_copy(tmp_path, mutant.check)
    assert explored.package.parent == copied
    assert explored.violated == mutant.reported_by, explored.output


def test_every_property_has_a_mutant_it_reports():
    assert {mutant.reported_by for mutant in MUTANTS} == set(explore.PROPERTIES)
