from django.db import models
from django.db.models.base import ModelBase
from django.utils.translation import (ugettext_lazy as _, ugettext)
from django.contrib.auth.models import User
from django.db.models.loading import get_model
from django.db.models import signals, Sum

_vote_models = { }
_rating_models = { }

def handle_rating_deleted(signal, sender, **kwargs):
    """
    When a rating is removed we need to update the summary aswell.
    """

    rating = kwargs['instance']

    summary = rating.object.rating_summary
    summary.rating_total -= rating.value
    summary.rating_count -= 1
    summary.save()

class VotesField(object):
    """
    Usage:

    class MyModel(models.Model):
        ...
        Votes = VotesField()
    """
    def __init__(self):
        pass

    def contribute_to_class(self, cls, name):
        self._name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def finalize(self, sender, **kwargs):
        descriptor = self._create_Vote_model(sender)
        setattr(sender, self._name, descriptor)
        self._add_methods(sender)

    def _create_Vote_model(self, model):
        class VoteSummaryMeta(ModelBase):
            """
            Make every VoteSummary model have their own name/table.
            """
            def __new__(c, name, bases, attrs):
                # Rename class
                name = '%sVoteSummary' % model._meta.object_name

                # This attribute is required for a model to function properly in Django.
                attrs['__module__'] = model.__module__

                vote_summary_model = ModelBase.__new__(c, name, bases, attrs)

                return vote_summary_model

        class VoteSummary(models.Model):
            """
            Vote Summary model
            """

            __metaclass__ = VoteSummaryMeta

            object = models.OneToOneField(model, verbose_name=_('object'))
            down_votes = models.PositiveIntegerField(default=0,
                                                     verbose_name=_('down votes'))
            up_votes = models.PositiveIntegerField(default=0,
                                                   verbose_name=_('up votes'))
            created_on = models.DateTimeField(auto_now_add=True, db_index=True,
                                              verbose_name=_('created on'),
                                              editable=False)
            updated_on = models.DateTimeField(auto_now=True, db_index=True,
                                              verbose_name=_('updated on'),
                                              editable=False)

            @property
            def total_votes(self):
                return self.up_votes + self.down_votes


            @property
            def up_pct(self):
                return float(self.up_votes) * 100 / self.total_votes

            @property
            def down_pct(self):
                return float(self.down_votes) * 100 / self.total_votes

            class Meta:
                ordering = ('object',)
                verbose_name = '%s Vote Summary' % model._meta.object_name
                verbose_name_plural = '%s Vote Summaries' % model._meta.object_name

            def __unicode__(self):
                return _('%s has %s down votes and %s up votes') % (self.object,
                                                                    self.down_votes,
                                                                    self.up_votes)

            @classmethod
            def get_model_name(self):
                return '%s.%s' % (self._meta.app_label, self._meta.object_name)

        class VoteMeta(ModelBase):
            """
            Make every Vote model have their own name/table.
            """
            def __new__(c, name, bases, attrs):
                # Rename class
                name = '%sVote' % model._meta.object_name

                # This attribute is required for a model to function properly in Django.
                attrs['__module__'] = model.__module__

                vote_model = ModelBase.__new__(c, name, bases, attrs)

                _vote_models[vote_model.get_model_name()] = vote_model

                return vote_model

        rel_nm_user = '%s_votes' % model._meta.object_name.lower()

        class Vote(models.Model):
            """
            Vote model
            """
            __metaclass__ = VoteMeta

            voter = models.ForeignKey(User, verbose_name=_('voter'))
            value = models.IntegerField(default=1, verbose_name=_('value'))
            date = models.DateTimeField(auto_now_add=True, db_index=True,
                                        verbose_name=_('voted on'))
            object = models.ForeignKey(model, verbose_name=_('object'))

            class Meta:
                ordering = ('date',)
                verbose_name = '%s Vote' % model._meta.object_name
                verbose_name_plural = '%s Votes' % model._meta.object_name

            def __unicode__(self):
                values = {
                            'voter': (self.voter.username if self.voter_id else 'Nobody'),
                            'like': ugettext('likes') if self.value > 0 else ugettext('does not like'),
                            'object': self.object_id if self.object_id else 'Nothing'
                          }
                return "%(voter)s %(like)s %(object)s" % values

            @classmethod
            def get_model_name(self):
                return '%s.%s' % (self._meta.app_label, self._meta.object_name)

            @classmethod
            def get_summary_model(self):
                return VoteSummary

            @classmethod
            def get_owner_model(self):
                return model

            def save(self, *args, **kwargs):
                """
                Save vote, and update summary.
                """
                if self.id:
                    last_value = Vote.objects.get(id=self.id).value
                else:
                    last_value = 0

                # First update the summary
                summary = self.object.vote_summary

                if last_value == 1:
                    summary.up_votes -= 1
                if last_value == -1:
                    summary.down_votes -= 1

                if self.value == 1:
                    summary.up_votes += 1
                if self.value == -1:
                    summary.down_votes += 1

                summary.save()

                # then save the vote
                super(Vote, self).save(*args, **kwargs)

        class VoteFieldDescriptor(object):
            def __get__(self, obj, objtype):
                """
                Return the related manager for the Votes.
                """
                if obj:
                    return getattr(obj, ('%svote_set' % model._meta.object_name).lower())
                else:
                    return Vote.objects

        self._votes_model = Vote
        self._vote_summary_model = VoteSummary
        return VoteFieldDescriptor()

    def _add_methods(self, model):
        """
        'model' is the Django Model who got the VotesField.
        Here we add some additional methods.
        """
        Vote = self._votes_model
        VoteSummary = self._vote_summary_model

        def summary(self):
            s, created = VoteSummary.objects.get_or_create(object=self)

            if created:
                s.down_votes = Vote.objects.filter(object=self, value= -1).count()
                s.up_votes = Vote.objects.filter(object=self, value=1).count()
                s.save()
            return s

        model.vote_summary = property(summary)
        model.vote_model = Vote
        model.vote_summary_model = VoteSummary


class RatingsField(object):
    """
    Usage:
    
    class MyModel(models.model):
        ...
        ratings = RatingsField()
    """

    def __init__(self):
        pass

    def contribute_to_class(self, cls, name):
        self._name = name
        models.signals.class_prepared.connect(self.finalize, sender=cls)

    def finalize(self, sender, **kwargs):
        descriptor = self._create_Rating_model(sender)
        setattr(sender, self._name, descriptor)
        self._add_methods(sender)

    def _create_Rating_model(self, model):
        class RatingSummaryMeta(ModelBase):
            """
            Make every RatingSummary model have their own name/table.
            """

            def __new__(c, name, bases, attrs):
                # Rename class
                name = '%sRatingSummary' % model._meta.object_name

                # This attribute is required for a model to function properly in Django.
                attrs['__module__'] = model.__module__

                rating_summary_model = ModelBase.__new__(c, name, bases, attrs)

                return rating_summary_model

        class RatingSummary(models.Model):
            """
            Rating Summary model
            """

            __metaclass__ = RatingSummaryMeta

            object = models.OneToOneField(model, verbose_name=_('object'))
            rating_count = models.PositiveIntegerField(default=0,
                                                       verbose_name=_('Rating count'),
                                                       null=False, blank=True)
            rating_total = models.PositiveIntegerField(default=0,
                                                       verbose_name=_('Rating total'),
                                                       null=False, blank=True)
            created_on = models.DateTimeField(auto_now_add=True, db_index=True,
                                              verbose_name=_('created on'),
                                              editable=False)
            updated_on = models.DateTimeField(auto_now=True, db_index=True,
                                              verbose_name=_('updated on'),
                                              editable=False)

            @property
            def rating(self):
                # Don't divide by zero
                if self.rating_count > 0:
                    return round(float(self.rating_total) / self.rating_count, 1)
                else:
                    return 0

            class Meta:
                ordering = ('object',)
                verbose_name = '%s Rating Summary' % model._meta.object_name
                verbose_name_plural = '%s Rating Summaries' % model._meta.object_name

            def __unicode__(self):
                return _('%s has an average rating of %s and has been rated %s times') % (self.object,
                                                                                          self.rating,
                                                                                          self.rating_count,)

            @classmethod
            def get_model_name(cls):
                return '%s.%s' % (self._meta.app_label, self._meta.object_name,)

        class RatingMeta(ModelBase):
            """
            Make every Rating model have their own name/table
            """

            def __new__(c, name, bases, attrs):
                # Rename class
                name = '%sRating' % model._meta.object_name

                # This attribute is required for a model to function properly in Django.
                attrs['__module__'] = model.__module__

                rating_model = ModelBase.__new__(c, name, bases, attrs)

                _rating_models[rating_model.get_model_name()] = rating_model

                return rating_model

        rel_nm_user = '%s_ratings' % model._meta.object_name.lower()

        class Rating(models.Model):
            """
            Rating model
            """

            __metaclass__ = RatingMeta

            rater = models.ForeignKey(User, verbose_name=_('rater'))
            value = models.IntegerField(default=0, verbose_name=_('value'))
            date = models.DateTimeField(auto_now_add=True, db_index=True,
                                        verbose_name=_('voted on'))
            object = models.ForeignKey(model, verbose_name=_('object'))

            class Meta:
                ordering = ('date',)
                verbose_name = '%s Rating' % model._meta.object_name
                verbose_name_plural = '%s Ratings' % model._meta.object_name

            def __unicode__(self):
                values = {
                            'rater': (self.rater.username if self.rater_id else 'Nobody'),
                            'rating': self.value,
                            'object': self.object_id if self.object_id else 'Nothing'
                          }
                return "%(rater)s gives %(object)s a rating of %(rating)s" % values

            @classmethod
            def get_model_name(self):
                return '%s.%s' % (self._meta.app_label, self._meta.object_name)

            @classmethod
            def get_summary_model(self):
                return RatingSummary

            @classmethod
            def get_owner_model(self):
                return model

            def save(self, *args, **kwargs):
                """
                Save rating, and update summary.
                """
                
                if self.id:
                    last_value = Rating.objects.get(id=self.id).value
                else:
                    last_value = 0

                # First update the summary
                summary = self.object.rating_summary

                if self.value == 0 and last_value > 0:
                    # Canceling rating.
                    
                    # subtract old value
                    summary.rating_total -= last_value
                    # decrease count by 1
                    summary.rating_count -= 1
                elif self.value > 0 and last_value > 0:
                    # Editing rating.
                    
                    # subtract old value
                    summary.rating_total -= last_value
                    # add new value
                    summary.rating_total += self.value
                elif self.value == 0 and last_value == 0:
                    # Initiating rating record. don't do anything                    
                    pass                    
                elif self.value > 0 and last_value == 0:
                    # New rating
                    
                    # add new value
                    summary.rating_total += self.value
                    # increase count by 1
                    summary.rating_count += 1

                summary.save()

                # then save the vote
                super(Rating, self).save(*args, **kwargs)

        class RatingFieldDescriptor(object):
            def __get__(self, obj, objtype):
                """
                Return the related manager for the Ratings.
                """
                if obj:
                    return getattr(obj, ('%srating_set' % model._meta.object_name).lower())
                else:
                    return Rating.objects

        self._ratings_model = Rating
        self._rating_summary_model = RatingSummary

        return RatingFieldDescriptor()

    def _add_methods(self, model):
        """
        'Model' is the Django Model who got the RatingsField.
        Here we add some additional methods.
        """

        Rating = self._ratings_model
        RatingSummary = self._rating_summary_model

        def summary(self):
            s, created = RatingSummary.objects.get_or_create(object=self)

            if created:
                count = Rating.objects.filter(object=self).count()
                sum = Rating.objects.filter(object=self).aggregate(sum=Sum('value'))
                s.rating_total = sum['sum'] if sum['sum'] else 0
                s.rating_count = count
                s.save()

            return s

        model.rating_summary = property(summary)
        model.rating_model = Rating
        model.rating_summary_model = RatingSummary

        # Connect a signal to handle delete of a Rating
        signals.post_delete.connect(handle_rating_deleted, sender=Rating)

