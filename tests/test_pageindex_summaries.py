import build_pageindex_summaries as bs


def test_short_sections_are_copied_without_model():
    node = {'node_id': '0001', 'title': 'Kurz', 'text': '## Kurz\n\nTrommel   reinigen, Sieb prüfen.'}
    def no_llm(_):
        raise AssertionError('kurze Abschnitte brauchen kein Modell')
    assert bs.build_summary(node, no_llm) == ('Trommel reinigen, Sieb prüfen.', False)


def test_codes_lead_the_summary_and_survive_truncation():
    text = 'Anzeige E:23 und E:18: ' + 'Wasser ' * 80
    raw = '"Störungsanzeigen: Laugenpumpe verstopft, Bodenwanne, Wasserhahn, Kundendienst rufen"'
    summary = bs.normalize_summary(raw, text, max_chars=60)
    assert summary.startswith('E:18, E:23 · Störungsanzeigen')
    assert len(summary) <= 60 and not summary.endswith(',')


def test_model_chatter_is_stripped():
    raw = 'Stichwortzeile: „Kindersicherung aktivieren und deaktivieren, Tasten 3 Sekunden“\nWeitere Hinweise …'
    assert bs.normalize_summary(raw, 'x' * 200) == 'Kindersicherung aktivieren und deaktivieren, Tasten 3 Sekunden'


def test_empty_model_answer_falls_back_to_text():
    node = {'node_id': '0002', 'title': 'Lang', 'text': 'Laugenpumpe reinigen. ' * 20}
    summary, via_model = bs.build_summary(node, lambda _: '')
    assert via_model and summary.startswith('Laugenpumpe reinigen.')


def test_prompt_category_labels_are_removed():
    raw = 'Thema: Verpackung/Altgerät; Bauteile: Elektro-Altgeräte; Bedienelemente: -; Handgriffe: Entsorgen'
    assert bs.normalize_summary(raw, 'x' * 200) == 'Verpackung/Altgerät; Elektro-Altgeräte; Entsorgen'


def test_heading_only_section_gives_empty_summary():
    assert bs.plain_text('## Umweltschutz') == ''
