#!/usr/bin/env python

import models
import phantom_users.phantom_util
import testutil
import unittest2

from google.appengine.ext import db
from mock import patch

class UsernameTest(testutil.GAEModelTestCase):
    def tearDown(self):
        # Clear all usernames just to be safe
        for u in models.UniqueUsername.all():
            u.delete()
        super(UsernameTest, self).tearDown()

    def test_user_name_fuzzy_match(self):
        """ Tests user name search can ignore periods properly. """
        def k(n):
            return models.UniqueUsername.build_key_name(n)

        self.assertEqual(k('mr.pants'), k('mrpants'))
        self.assertEqual(k('mr.pants...'), k('mrpants'))
        self.assertEqual(k('mrpants'), k('mrpants'))
        self.assertEqual(k('MrPants'), k('mrpants'))

    def validate(self, username):
        return models.UniqueUsername.is_valid_username(username)

    def test_bad_user_name_fails_validation(self):
        self.assertFalse(self.validate(''))
        self.assertFalse(self.validate('a')) # Too short
        self.assertFalse(self.validate('aa')) # Still too short
        self.assertFalse(self.validate('4scoresand7years')) # Must start with letter
        self.assertFalse(self.validate('.dotsarebadtoo'))
        self.assertFalse(self.validate('!nvalid'))
        self.assertFalse(self.validate('B@dCharacters'))
        self.assertFalse(self.validate('I cannot read instructions'))
        self.assertFalse(self.validate(u'h\u0400llojello')) # Cyrillic chars
        self.assertFalse(self.validate('mrpants@khanacademy.org'))

    def test_good_user_name_validates(self):
        self.assertTrue(self.validate('poopybutt'))
        self.assertTrue(self.validate('mrpants'))
        self.assertTrue(self.validate('instructionsareeasy'))
        self.assertTrue(self.validate('coolkid1983'))

    def make_user(self, email):
        u = models.UserData.insert_for(email, email)
        u.put()
        return u

    def test_claiming_username_works(self):
        u1 = self.make_user("bob")
        u2 = self.make_user("robert")

        # Free
        self.assertTrue(u1.claim_username("superbob"))
        self.assertEqual("superbob", u1.username)

        # Now it's taken
        self.assertFalse(u2.claim_username("superbob"))

        # But something completely different should still be good
        self.assertTrue(u2.claim_username("sadbob"))
        self.assertEqual("sadbob", u2.username)

    def test_releasing_usernames(self):
        clock = testutil.MockDatetime()
        u1 = self.make_user("bob")
        u2 = self.make_user("robert")

        # u1 gets "superbob", but changes his mind.
        self.assertTrue(u1.claim_username("superbob", clock))
        self.assertEqual("superbob", u1.username)
        self.assertTrue(u1.claim_username("ultrabob", clock))
        self.assertEqual("ultrabob", u1.username)

        # TOTAL HACK - for some reason without this read (which shouldn't
        # actually have any side effect), the following assert fails because
        # there's no strong consistency ensured on the HRD.
        db.get([u1.key()])
        self.assertEqual(
                u1.user_id,
                models.UserData.get_from_username("ultrabob").user_id)
        self.assertEqual(
                None,
                models.UserData.get_from_username("superbob"))

        # Usernames go into a holding pool, even after they're released
        self.assertFalse(u2.claim_username("superbob", clock))

        # Note that the original owner can't even have it back
        self.assertFalse(u1.claim_username("superbob", clock))

        # Still no good at the border of the holding period
        clock.advance(models.UniqueUsername.HOLDING_PERIOD_DELTA)
        self.assertFalse(u2.claim_username("superbob", clock))

        # OK - now u2 can have it.
        clock.advance_days(1)
        self.assertTrue(u2.claim_username("superbob", clock))
        self.assertEqual("superbob", u2.username)

        db.get([u2.key()])
        self.assertEqual(
                u2.user_id,
                models.UserData.get_from_username("superbob").user_id)

class ProfileSegmentTest(testutil.GAEModelTestCase):
    def to_url(self, user):
        return user.prettified_user_email
    def from_url(self, segment):
        return models.UserData.get_from_url_segment(segment)

    def create_phantom(self):
        user_id = phantom_users.phantom_util._create_phantom_user_id()
        return models.UserData.insert_for(user_id, user_id)

    def test_url_segment_generation(self):
        # Pre-phantom users can't have profile URL's
        prephantom = models.UserData.pre_phantom()
        self.assertTrue(self.from_url(self.to_url(prephantom)) is None)

        # Phantom users can't have profile URL's
        phantom = self.create_phantom()
        self.assertTrue(self.from_url(self.to_url(phantom)) is None)

        # Normal users are cool, though.
        bob = models.UserData.insert_for(
                "http://googleid.khanacademy.org/1234",
                "bob@gmail.com")
        bob.put()
        self.assertEqual(
                self.from_url(self.to_url(bob)).user_id,
                bob.user_id)

        sally = models.UserData.insert_for(
                "http://facebookid.khanacademy.org/1234",
                "http://facebookid.khanacademy.org/1234")
        sally.put()
        self.assertEqual(
                self.from_url(self.to_url(sally)).user_id,
                sally.user_id)

class PromoRecordTest(testutil.GAEModelTestCase):
    # Shorthand
    def r(self, promo_name, user_id):
        return models.PromoRecord.record_promo(promo_name, user_id)
    
    def test_promo_record(self):
        u1 = "http://facebookid.khanacademy.org/1234"
        u2 = "http://googleid.khanacademy.org/5678"
        p1 = "Public profiles"
        p2 = "Skynet"

        # First time
        self.assertTrue(self.r(p1, u1))
        # Second time and onwards
        for i in range(10):
            self.assertFalse(self.r(p1, u1))
            
        # Different user
        self.assertTrue(self.r(p1, u2))
        
        # Different promo
        self.assertTrue(self.r(p2, u1))

class VideoSubtitlesTest(unittest2.TestCase):
    def test_get_key_name(self):
        kn = models.VideoSubtitles.get_key_name('en', 'YOUTUBEID')
        self.assertEqual(kn, 'en:YOUTUBEID')

    def test_load_valid_json(self):
        subs = models.VideoSubtitles(json='[{"text":"subtitle"}]')
        json = subs.load_json()
        self.assertIsNotNone(json)
        self.assertEqual([{u'text': u'subtitle'}], json)

    @patch('models.logging.warn')
    def test_log_warning_on_invalid_json(self, warn):
        subs = models.VideoSubtitles(json='invalid json')
        json = subs.load_json()
        self.assertIsNone(json)
        self.assertEqual(warn.call_count, 1, 'logging.warn() not called')
