"""A malformed pre-check answer is asked again: one bad model answer never fails a page (comic_preflight_invalid)."""

import pytest

from book_comic import preflight
from book_comic.preflight import PREFLIGHT_CALLS, review_page
from conftest import FakeVision

HERO_STANDS = {'subject': 'Hero', 'attribute': 'pose', 'expected': 'standing'}
SCRIPT = {'cast': {'characters': [{'name': 'Noa', 'name_en': 'Hero'}], 'props': []}, 'cover': {'scene': 'Hero stands.'},
          'panels': [{'scene': 'Hero stands at the door.', 'caption': '', 'dialogue': []}]}
PASSED = {'action_continuity': True, 'text_agreement': True, 'design_continuity': True}
GOOD = {**PASSED, 'panels': [{'requirements': [HERO_STANDS]}], 'cover_requirements': []}
MALFORMED = [
    {**PASSED, 'panels': [], 'cover_requirements': []},                                         # a panel is missing
    {**PASSED, 'panels': 'none', 'cover_requirements': []},                                     # not a list
    {**PASSED, 'panels': [{'requirements': None}], 'cover_requirements': []},                   # no requirements list
    {**PASSED, 'panels': [{'requirements': [{'subject': 'Hero', 'attribute': 'mood', 'expected': 'calm'}]}], 'cover_requirements': []},
    {**PASSED, 'panels': [{'requirements': [{'subject': 'Hero', 'attribute': 'pose'}]}], 'cover_requirements': []},
    {**PASSED, 'panels': [{'requirements': [HERO_STANDS] * 9}], 'cover_requirements': []},      # more than eight
    {**PASSED, 'panels': [{'requirements': [{**HERO_STANDS, 'expected': 'x' * 181}]}], 'cover_requirements': []},
    {**PASSED, 'panels': [{'requirements': [HERO_STANDS]}], 'cover_requirements': 'none'},
]


def answers(*sequence):
    """A vision fake that gives each answer in turn (an exception is raised), repeating the last."""
    left = list(sequence)

    def answer(prompt, image):
        value = left.pop(0) if len(left) > 1 else left[0]
        if isinstance(value, Exception):
            raise value
        return value
    return FakeVision(answer)


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    slept = []
    monkeypatch.setattr(preflight.time, 'sleep', slept.append)
    return slept


@pytest.mark.parametrize('malformed', MALFORMED)
def test_one_malformed_answer_is_asked_again_and_the_page_goes_on(malformed, waits):
    vision = answers(malformed, GOOD)
    reviewed = review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == 2 and vision.prompts[0] == vision.prompts[1]
    assert reviewed['panels'][0]['requirements'] == [HERO_STANDS]
    assert waits == []  # the model answered: nothing to wait for


def test_an_answer_that_stays_malformed_still_fails_after_a_bounded_number_of_asks():
    vision = answers(MALFORMED[0])
    with pytest.raises(ValueError, match='^comic_preflight_invalid$'):
        review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == PREFLIGHT_CALLS == 3


def test_a_failed_call_or_unparseable_json_is_asked_again_after_a_wait(waits):
    vision = answers(ValueError('Expecting value: line 1'), GOOD)
    assert review_page(SCRIPT, vision, include_cover=False)['panels'][0]['requirements'] == [HERO_STANDS]
    assert len(vision.prompts) == 2 and waits == [preflight.PREFLIGHT_BACKOFF_SECONDS[0]]


def test_a_checker_that_never_answers_is_still_unavailable(waits):
    vision = answers(TimeoutError('provider detail'))
    with pytest.raises(ValueError, match='^comic_preflight_unavailable$'):
        review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == PREFLIGHT_CALLS and waits == list(preflight.PREFLIGHT_BACKOFF_SECONDS)


@pytest.mark.parametrize('verdict', [{**GOOD, 'text_agreement': False}, {}, ['not', 'an', 'object']])
def test_a_real_failed_verdict_is_never_asked_again(verdict):
    vision = answers(verdict, GOOD)
    with pytest.raises(ValueError, match='^comic_preflight_failed$'):
        review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == 1


def test_a_failed_verdict_after_a_malformed_answer_still_fails():
    vision = answers(MALFORMED[0], {**GOOD, 'action_continuity': False}, GOOD)
    with pytest.raises(ValueError, match='^comic_preflight_failed$'):
        review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == 2


@pytest.mark.parametrize('cover', [{}, {'cover_requirements': None}])
def test_a_page_without_a_cover_needs_no_cover_requirements_in_the_answer(cover):
    # A paid page sends no cover scene; an answer that leaves the cover list out says the same as an empty one.
    answer = {**PASSED, 'panels': [{'requirements': [HERO_STANDS]}], **cover}
    vision = answers(answer)
    reviewed = review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == 1 and reviewed['cover']['requirements'] == []


def test_a_cover_page_still_needs_its_cover_requirements():
    vision = answers({**PASSED, 'panels': [{'requirements': [HERO_STANDS]}]})
    with pytest.raises(ValueError, match='^comic_preflight_invalid$'):
        review_page(SCRIPT, vision, include_cover=True)
    assert len(vision.prompts) == PREFLIGHT_CALLS


def test_extra_keys_on_a_requirement_are_dropped_not_fatal():
    noisy = {**HERO_STANDS, 'index': 0, 'reason': 'the scene says so'}
    vision = answers({**PASSED, 'panels': [{'requirements': [noisy]}], 'cover_requirements': []})
    reviewed = review_page(SCRIPT, vision, include_cover=False)
    assert len(vision.prompts) == 1 and reviewed['panels'][0]['requirements'] == [HERO_STANDS]
