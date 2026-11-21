"""Clock rules applied by the voice agent (agents/interview_monitor.py)."""

from agents.interview_monitor import End, InterviewMonitor, Notify, Say


def asked(m, at):
    """The interviewer finished asking something at `at`."""
    m.agent_started_speaking(at - 3)
    m.agent_stopped_speaking(at)


def run(m, start, end, step=1.0):
    """Tick from start to end; return (time, action) pairs. Nudges are spoken
    straight away, as the agent does."""
    out, t = [], start
    while t <= end:
        for a in m.tick(t):
            out.append((t, a))
            if isinstance(a, Say):
                m.agent_started_speaking(t)
                m.agent_stopped_speaking(t)
        t += step
    return out


def test_silence_offers_repeat_then_moves_on():
    m = InterviewMonitor(now=0)
    asked(m, 0)
    actions = run(m, 1, 31)
    assert actions == [(10, Say("repeat_offer")), (30, Notify("question_unanswered"))]


def test_own_nudge_doesnt_restart_the_question_clock():
    m = InterviewMonitor(now=0)
    asked(m, 0)
    assert m.tick(10) == [Say("repeat_offer")]
    m.agent_started_speaking(10)
    m.agent_stopped_speaking(13)  # the nudge itself
    assert m.tick(30) == [Notify("question_unanswered")]


def test_answering_records_thinking_time_and_resets():
    m = InterviewMonitor(now=0)
    asked(m, 0)
    m.user_started_speaking(7.5)
    assert m.take_latency_ms() == 7500 and m.take_latency_ms() is None
    assert run(m, 8, 60) == []  # no question pending


def test_three_unanswered_in_a_row_ends_the_interview():
    m = InterviewMonitor(now=0)
    results = []
    for start in (0, 40, 80):
        asked(m, start)
        results += [a for _, a in run(m, start + 1, start + 31) if not isinstance(a, Say)]
    assert results == [Notify("question_unanswered"), Notify("question_unanswered"), End("no_response")]
    assert m.tick(200) == []  # ended


def test_total_unanswered_silence_ends_even_with_answers_between():
    m = InterviewMonitor(now=0)
    t, ends = 0, []
    for _ in range(4):
        asked(m, t)
        ends += [a for _, a in run(m, t + 1, t + 31) if isinstance(a, End)]
        t += 40
        asked(m, t)
        m.user_started_speaking(t + 2)  # answers the next one
        t += 10
    assert ends == [End("no_response")]  # the 4th unanswered = 2 minutes


def test_one_rejoin_within_two_minutes():
    m = InterviewMonitor(now=0)
    assert m.participant_left(10) == []
    assert run(m, 11, 100) == []  # waiting for them
    assert m.participant_joined(100) == [Notify("candidate_returned")]
    assert m.participant_left(200) == [End("disconnected")]  # second drop

    m = InterviewMonitor(now=0)
    m.participant_left(10)
    assert m.tick(130) == [End("disconnected")]


def test_nothing_happens_while_the_interviewer_speaks():
    m = InterviewMonitor(now=0)
    asked(m, 0)
    m.agent_started_speaking(5)
    assert run(m, 6, 60) == []


def test_hang_up_fallback():
    m = InterviewMonitor(now=0)
    m.participant_left(0)
    m.participant_joined(1)
    assert m.participant_left(2) == [End("disconnected")]
    # The worker's goodbye never came: hang up 60 s after the end anyway
    assert not m.should_hang_up_anyway(61) and m.should_hang_up_anyway(62)


def test_failed_nudge_doesnt_confuse_the_next_question():
    m = InterviewMonitor(now=0)
    asked(m, 0)
    assert m.tick(10) == [Say("repeat_offer")]
    m.prompt_failed()  # the agent couldn't speak it
    asked(m, 20)  # a real question: its clock starts now
    acts = run(m, 21, 50)
    assert acts == [(30, Say("repeat_offer")), (50, Notify("question_unanswered"))]
