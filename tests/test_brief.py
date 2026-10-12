"""The brief validator must reject anything the model could get wrong without us noticing."""
import unittest

from core.brief import render_text, validate

FACTS = {
    'sales': dict(value=564027.83, fmt='money', label='Sales', source='x'),
    'yoy': dict(value=0.1285, fmt='pct_signed', label='Change', source='x'),
    'drop': dict(value=-6312.0, fmt='money_signed', label='Change', source='x'),
    'name': dict(value='Tabby', fmt='text', label='Name', source='x'),
    'old': dict(value=163, fmt='int', label='Before', source='x'),
    'new': dict(value=158, fmt='int', label='After', source='x'),
}


def brief(*items, headline='Sales are {yoy} vs last year.'):
    return dict(headline=headline, sections=[dict(title='What happened', items=[dict(kind=k, text=t) for k, t in items])])


class ValidateBrief(unittest.TestCase):
    def test_accepts_a_clean_brief(self):
        v = validate(brief(('fact', 'Sales reached {sales}, {yoy} vs last year.'),
                           ('fact', 'Returning customers spent {drop|abs} less.'),
                           ('action', 'Reorder {name}.')), FACTS)
        self.assertTrue(v['passed'], v['errors'])
        self.assertEqual(v['numbers_checked'], 4)

    def test_rejects_a_number_typed_by_hand(self):
        v = validate(brief(('fact', 'Sales reached {sales}, up 12.8% vs last year.')), FACTS)
        self.assertFalse(v['passed'])
        self.assertIn('typed by hand', v['errors'][0])

    def test_rejects_a_digit_in_the_headline(self):
        v = validate(brief(('fact', 'Sales reached {sales}.'), headline='Sales up 13%'), FACTS)
        self.assertFalse(v['passed'])

    def test_rejects_an_unknown_fact(self):
        v = validate(brief(('fact', 'Margin was {margin}.')), FACTS)
        self.assertFalse(v['passed'])
        self.assertIn('unknown fact', v['errors'][0])

    def test_rejects_hiding_the_sign_of_a_positive_change(self):
        v = validate(brief(('fact', 'Sales fell {yoy|abs}.')), FACTS)
        self.assertFalse(v['passed'])

    def test_rejects_hiding_a_negative_sign_without_saying_it_went_down(self):
        v = validate(brief(('fact', 'Returning customers spent {drop|abs}.')), FACTS)
        self.assertFalse(v['passed'])
        self.assertIn('does not say it went down', v['errors'][0])

    def test_rejects_a_gain_described_as_a_decline(self):
        v = validate(brief(('fact', 'Sales fell {yoy} vs last year.')), FACTS)
        self.assertFalse(v['passed'])
        self.assertIn('describes a decline', v['errors'][0])

    def test_rejects_a_decline_described_as_growth(self):
        v = validate(brief(('fact', 'Returning customers added {drop}.')), FACTS)
        self.assertFalse(v['passed'])
        self.assertIn('describes growth', v['errors'][0])

    def test_reads_each_clause_on_its_own(self):
        v = validate(brief(('fact', 'Sales grew {yoy} while returning customers spent {drop|abs} less.')), FACTS)
        self.assertTrue(v['passed'], v['errors'])

    def test_direction_words_must_be_whole_words(self):
        # "update" contains "up", "download" contains "down": neither is a direction word.
        v = validate(brief(('fact', 'In this update, returning customers moved {drop}.')), FACTS)
        self.assertTrue(v['passed'], v['errors'])

    def test_from_to_must_match_the_direction_word(self):
        self.assertTrue(validate(brief(('fact', 'Returning customers fell from {old} to {new}.')), FACTS)['passed'])
        self.assertFalse(validate(brief(('fact', 'Returning customers rose from {old} to {new}.')), FACTS)['passed'])
        self.assertFalse(validate(brief(('fact', 'Returning customers fell from {new} to {old}.')), FACTS)['passed'])

    def test_fact_sentences_must_cite_a_fact(self):
        v = validate(brief(('fact', 'Sales were strong.')), FACTS)
        self.assertFalse(v['passed'])

    def test_rejects_a_bad_kind(self):
        self.assertFalse(validate(brief(('opinion', 'Sales reached {sales}.')), FACTS)['passed'])

    def test_renders_values_from_the_data(self):
        self.assertEqual(render_text('{sales}, {yoy}, {drop|abs} less, {name}', FACTS), '$564.0K, +12.8%, $6.3K less, Tabby')


if __name__ == '__main__':
    unittest.main()
