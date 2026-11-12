"""scripts/spec_drift.py: what has moved upstream since we last looked. The network parts are not run here; the parsing, the comparison
of recorded dates and the report are."""

import json

import spec_drift as sd


def test_a_date_in_a_status_line():
    assert sd.date_in_status("W3C Working Draft 09 November 2026") == "2026-11-09"
    assert sd.date_in_status("W3C Candidate Recommendation Draft 1 April 2026") == "2026-04-01"
    assert sd.date_in_status("no date here") is None
    assert sd.date_in_status("12 Smarch 2026") is None


def test_the_date_of_a_tr_page():
    head = 'var respecConfig = {"generatedSubtitle": "W3C Working Draft 05 November 2026", "publishISODate": "2026-11-05T00:00:00.000Z"};'
    assert sd.tr_date(head) == ("2026-11-05", "W3C Working Draft 05 November 2026")
    assert sd.tr_date('{"generatedSubtitle": "W3C Working Draft 05 November 2026"}')[0] == "2026-11-05"
    assert sd.tr_date("nothing")[0] is None


def test_the_date_a_snapshot_or_a_grammar_table_records(tmp_path):
    snap = tmp_path / "s.txt"
    snap.write_text("RDF 1.2 Turtle\nStatus at fetch time: W3C Working Draft 11 November 2026\nPublished: 2026-11-11\n=====\n")
    assert sd.artifact_date("snapshot", snap) == "2026-11-11"
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"document": "W3C Working Draft 09 November 2026", "productions": []}))
    assert sd.artifact_date("json", table) == "2026-11-09"
    assert sd.artifact_date("json", tmp_path / "missing.json") is None


def test_a_pin_is_read_from_a_download_script(tmp_path):
    script = tmp_path / "d.py"
    script.write_text('REPO = "w3c/x"\nPINNED_SHA = "' + "ab" * 20 + '"\n')
    assert sd.pinned_sha(script) == "ab" * 20
    script.write_text("nothing\n")
    assert sd.pinned_sha(script) is None


def test_upstream_file_changes_are_counted_per_vendored_subtree():
    files = [
        {"filename": "rdf/rdf12/rdf-turtle/syntax/a.ttl", "status": "added"},
        {"filename": "rdf/rdf12/rdf-turtle/syntax/b.ttl", "status": "modified"},
        {"filename": "rdf/rdf12/rdf-turtle/syntax/c.ttl", "status": "removed"},
        {"filename": "rdf/rdf12/reports/x.ttl", "status": "renamed", "previous_filename": "rdf/rdf12/old/x.ttl"},
        {"filename": "sparql/sparql11/csv-tsv-res/csv04.csv", "status": "added"},
        {"filename": "README.md", "status": "modified"},
        {"filename": "rdf/rdf11/a.ttl", "status": "modified"},
    ]
    got = sd.summarise_files(files, ["rdf/rdf12/", "sparql/sparql11/", "sparql/sparql12/"])
    assert got == {"rdf/rdf12/": {"added": 1, "modified": 1, "removed": 1, "renamed": 1}, "sparql/sparql11/": {"added": 1}}


def test_every_pin_group_reads_a_sha_from_its_scripts():
    for name, (_repo, _branch, scripts, _subtrees) in sd.PINS.items():
        shas = {sd.pinned_sha(p) for p in scripts}
        assert len(shas) == 1 and None not in shas, (name, shas)


def test_every_tracked_spec_has_a_recorded_date():
    recorded = json.loads(sd.DATES_FILE.read_text(encoding="utf8"))
    assert set(recorded["specs"]) == set(sd.SPECS), "run: python scripts/spec_drift.py --record after a review"


def test_no_vendored_copy_is_older_than_the_last_review():
    """The offline check: a snapshot or grammar table older than the recorded date of its spec is a vendored copy someone forgot to refresh."""
    rows = sd.check_specs(sd.load_dates(), offline=True)
    stale = [(r["spec"], r["vendored"], r["recorded"], r["status"]) for r in rows if r["status"] != "current"]
    assert not stale, stale


def test_the_report_says_what_moved_and_the_exit_code_follows():
    moved = {"reviewed": "2026-11-01", "specs": [{"spec": "shacl12-ui", "recorded": "2026-11-06", "live": "2026-11-11", "vendored": None,
                                                    "status": "moved since the last review (2026-11-06)"}],
             "pins": [{"suite": "w3c/data-shapes", "pin": "47c6e078b", "changed": {"shacl12-test-suite/": {"modified": 3}}, "status": "2 commits ahead; the vendored subtrees changed"}],
             "vocabularies": []}
    text = sd.render(moved)
    assert "shacl12-ui" in text and "moved since the last review" in text and "3 modified" in text
    assert sd.drifted(moved) and not sd.broken(moved)
    current = {"reviewed": "x", "specs": [{"status": "current"}], "pins": [{"status": "current (4 upstream commits, none in the vendored subtrees)"}],
               "vocabularies": [{"status": "current"}]}
    assert not sd.drifted(current) and not sd.broken(current)
    unreachable = {"reviewed": "x", "specs": [{"status": "could not check"}], "pins": [], "vocabularies": []}
    assert not sd.drifted(unreachable) and sd.broken(unreachable)


def test_an_unknown_spec_to_record_is_an_error(capsys):
    assert sd.main(["--record", "no-such-spec"]) == 2
    assert "unknown spec" in capsys.readouterr().err
