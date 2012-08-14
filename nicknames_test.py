#!/user/bin/env python

import models
import testutil

class NicknamesTest(testutil.GAEModelTestCase):

    def setUp(self):
        super(NicknamesTest, self).setUp()
        self.user_count = 0

    def assertSingleResult(self, expected, raw_query):
        matches = models.NicknameIndex.users_for_search(raw_query)
        self.assertEqual(1, len(matches),
                         "Expected exactly 1 result for \"%s\"" % raw_query)
        self.assertEqual(expected, matches[0])

    def make_user(self, nickname):
        u = models.UserData(key_name="key_%s" % self.user_count)
        u.user_id = "userid_%s" % self.user_count
        u.update_nickname(nickname)
        u.put()

        self.user_count += 1
        return u

    def test_retrieve_user_by_nickname(self):
        u = self.make_user('Fake User One')

        for raw_query in ['Fake', 'uSeR', 'ONE', 'fake user one']:
            self.assertSingleResult(u.key(), raw_query)

        user_matches = models.NicknameIndex.users_for_search('does not exist')
        self.assertEqual(0, len(user_matches))

    def test_retrieval_order_agnostic(self):
        u = self.make_user('Firstname Middlename Lastname')

        # Order of tokens doesn't matter (name order differs by culture anyways)
        for raw_query in ['Lastname, Firstname',
                          'Firstname Lastname',
                          'lastname firstname middlename']:
            self.assertSingleResult(u.key(), raw_query)

    def test_multi_user_search(self):
        han_solo = self.make_user('Han Solo')
        leia = self.make_user('Leia Organa Solo')
        jabba = self.make_user('Jabba the Hutt')

        for raw_query in ['Han Solo', 'Han']:
            self.assertSingleResult(han_solo.key(), raw_query)

        for raw_query in ['Leia']:
            self.assertSingleResult(leia.key(), raw_query)

        for raw_query in ['Jabba', 'the Hutt', 'jabba the HUTT']:
            self.assertSingleResult(jabba.key(), raw_query)

        matches = models.NicknameIndex.users_for_search('Solo')
        self.assertEquals(2, len(matches))
        self.assertEquals(set([han_solo.key(), leia.key()]), set(matches))

    def test_partial_matches(self):
        self.make_user('Firstname Middlename Lastname')

        # Partial matches on a full search should _not_ be returned.
        for raw_query in ['lastn', 'firstname mid', 'firstname wronglast']:
            user_matches = models.NicknameIndex.users_for_search(raw_query)
            self.assertEqual(0, len(user_matches))
