from conftest import words

from live_notes_api.trigger import TriggerConfig, TriggerPolicy


def test_nothing_without_text():
    p = TriggerPolicy()
    assert p.decide(100_000) is None


def test_a_fires_at_50_words_only():
    p = TriggerPolicy()
    p.add_segment(words(49), 1000)
    assert p.decide(1000) is None
    p.add_segment("one more", 2000)
    d = p.decide(2000)
    assert d and d.reason == "A" and not d.revision


def test_b_after_25s_with_any_words():
    p = TriggerPolicy()
    p.start_tick(0)
    p.end_tick()
    p.add_segment("just a few words", 1000)
    assert p.decide(24_999) is None
    assert p.decide(25_000).reason == "B"


def test_b_first_tick_counts_from_first_pending_text():
    p = TriggerPolicy()
    p.add_segment("hello there", 10_000)
    assert p.decide(34_999) is None
    assert p.decide(35_000).reason == "B"


def test_c_slide_change_even_without_words():
    p = TriggerPolicy()
    p.slide_changed()
    assert p.decide(0).reason == "C"


def test_d_cues_fire_immediately_and_flag_revision():
    for cue in [
        "sorry",
        "I meant",
        "Correction",
        "that should be",
        "let me rephrase",
        "actually no",
        "Actually, no",
    ]:
        p = TriggerPolicy()
        p.add_segment(f"so the value is five {cue} six", 500)
        d = p.decide(500)
        assert d and d.reason == "D" and d.revision, cue


def test_no_false_cue():
    p = TriggerPolicy()
    p.add_segment("this is a sorrel horse and the correctional facility", 0)
    assert p.decide(0) is None


def test_min_spacing_except_d():
    p = TriggerPolicy()
    p.start_tick(10_000)
    p.end_tick()
    p.add_segment(words(60), 11_000)
    assert p.decide(17_999) is None  # A is ready but < 8 s since the last start
    assert p.decide(18_000).reason == "A"
    p.slide_changed()
    assert p.decide(12_000) is None
    p.cue_pending = False
    p.add_segment("sorry I meant the other one", 12_000)
    assert p.decide(12_000).reason == "D"  # D ignores spacing


def test_single_flight():
    p = TriggerPolicy()
    p.add_segment(words(60), 0)
    p.start_tick(0)
    p.add_segment("sorry, correction", 100)
    p.slide_changed()
    assert p.in_flight and p.decide(60_000) is None
    p.end_tick()
    # what arrived during the tick is still pending and fires as soon as spacing allows
    d = p.decide(100)
    assert d.reason == "D"
    assert p.words == 2


def test_start_tick_consumes_and_abort_restores():
    p = TriggerPolicy()
    p.add_segment(words(60) + " sorry", 0)
    p.slide_changed()
    taken = p.start_tick(0)
    assert p.words == 0 and not p.slide_pending and not p.cue_pending
    p.abort_tick(taken)
    assert p.words == 61 and p.slide_pending and p.cue_pending and not p.in_flight


def test_flush_ignores_thresholds_and_spacing():
    p = TriggerPolicy()
    p.start_tick(1000)
    p.end_tick()
    p.add_segment("two words", 1100)
    assert p.decide(1200) is None
    p.request_flush()
    d = p.decide(1200)
    assert d.reason == "flush" and not d.revision


def test_thresholds_configurable():
    p = TriggerPolicy(
        TriggerConfig(words_threshold=5, max_gap_ms=1000, min_spacing_ms=0, cues=("whoops",))
    )
    p.add_segment("one two three four five", 0)
    assert p.decide(0).reason == "A"
    q = TriggerPolicy(TriggerConfig(cues=("whoops",)))
    q.add_segment("I am sorry about that", 0)
    assert q.decide(0) is None  # default cues replaced
    q.add_segment("whoops", 0)
    assert q.decide(0).reason == "D"
