"""A closing action in progress ("pushes the drawer shut") is not a requirement that the object is already closed."""

import pytest
from PIL import Image

from book_comic.art_check import inspect_art
from book_comic.preflight import REVIEW_PROMPT, _explicit_requirements, review_page
from book_comic.staging_tolerance import PROGRESS_NOTE
from conftest import FakeVision

DRAWER_CLOSED = {'subject': 'drawer', 'attribute': 'state', 'expected': 'closed'}
SUBJECTS = ['Hero', 'drawer', 'cabinet door']


def reviewed(scene, requirements):
    script = {'cast': {'characters': [{'name': 'Noa', 'name_en': 'Hero'}], 'props': [{'name': 'drawer', 'look': 'oak drawer'}]},
              'cover': {'scene': ''}, 'panels': [{'scene': scene, 'caption': '', 'dialogue': []}]}
    answer = {'action_continuity': True, 'text_agreement': True, 'design_continuity': True,
              'panels': [{'requirements': requirements}], 'cover_requirements': []}
    return review_page(script, FakeVision(lambda p, i: answer), include_cover=False)['panels'][0]['requirements']


def test_pushes_the_drawer_shut_is_not_checked_as_drawer_closed():
    # The report: three draws of one panel failed "state: expected closed, saw open" while Hero was pushing the drawer.
    holds = {'subject': 'Hero', 'attribute': 'contact', 'expected': 'Hero pushes the drawer with one hand'}
    assert reviewed('Medium shot: Hero pushes the drawer shut.', [DRAWER_CLOSED, holds]) == [holds]


@pytest.mark.parametrize('scene', [
    'Hero pushes the drawer shut.',
    'Close-up: Hero pushes the heavy drawer shut with her hip, eyes on the window.',
    'Hero slams the drawer closed and turns to the door.',
    'Hero is pushing the drawer shut.',
    'Hero slides the drawer closed.',
    'Hero closes the drawer.',
    'Hero is closing the drawer.',
    'Hero shuts the drawer.',
    'Hero reaches out to shut the drawer.',
    'Hero starts to close the drawer.',
])
def test_a_closing_action_states_no_finished_state(scene):
    assert _explicit_requirements(scene, [DRAWER_CLOSED], SUBJECTS) == []


@pytest.mark.parametrize('scene', [
    'The drawer is closed.',
    'The drawer is firmly shut.',
    'The drawer stays shut while Hero searches the shelf.',
    'Hero rests a hand on the closed drawer.',
    'Hero presses both palms against the shut drawer.',
    'Hero has shut the drawer and leans on the desk.',
    'Hero has closed the drawer.',
    'Hero pushes at the drawer, which is already closed.',
    'Hero pushes the drawer shut. In the next moment the drawer is closed.',
])
def test_a_stated_closed_state_is_still_required(scene):
    assert _explicit_requirements(scene, [DRAWER_CLOSED], SUBJECTS) == [DRAWER_CLOSED]


def test_the_closing_action_does_not_lend_its_word_to_or_take_it_from_another_object():
    scene = 'Hero pushes the drawer shut. The cabinet door is closed.'
    door = {'subject': 'cabinet door', 'attribute': 'state', 'expected': 'closed'}
    assert _explicit_requirements(scene, [DRAWER_CLOSED, door], SUBJECTS) == [door]


@pytest.mark.parametrize('scene,state', [('Hero pulls the drawer open.', 'open'), ('Hero opens the drawer.', 'open'),
                                        ('The drawer is open.', 'open')])
def test_opening_is_unchanged_an_opening_drawer_is_drawn_open(scene, state):
    required = [{'subject': 'drawer', 'attribute': 'state', 'expected': state}]
    assert _explicit_requirements(scene, required, SUBJECTS) == required


def test_a_visibly_wrong_resting_state_still_fails_the_draw():
    answer = {'has_text': False, 'bad_anatomy': False, 'requirement_checks': [{'index': 0, 'observed': 'open', 'matches': False}]}
    found = inspect_art(Image.new('RGB', (64, 64)), FakeVision(lambda p, i: answer), requirements=[DRAWER_CLOSED])
    assert found['requirement_mismatch'] is True


def test_the_reviewer_and_the_checker_are_told_about_actions_in_progress():
    assert 'pushes the drawer shut' in REVIEW_PROMPT
    vision = FakeVision(lambda p, i: {'has_text': False, 'bad_anatomy': False, 'identity_mismatch': False,
                                      'design_mismatch': False, 'scene_mismatch': False})
    inspect_art(Image.new('RGB', (64, 64)), vision, context='Hero pushes the drawer shut.')
    assert PROGRESS_NOTE in vision.prompts[0] and 'pushing a drawer shut' in PROGRESS_NOTE
