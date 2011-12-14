from django.db import models
from django.db.models.base import ModelBase
from django.utils.translation import (ugettext_lazy as _, ugettext)
from django.contrib.auth.models import User
from django.db.models.loading import get_model

_vote_models = { }

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

            object = models.ForeignKey(model, verbose_name=_('object'))
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

            def save(self, *args, **kwargs):
                created = not self.id

                # first update the summary
                summary = self.object.vote_summary

                if self.value == 1:
                    summary.up_votes += 1
                    if not created:
                        summary.down_votes -= 1

                if self.value == -1:
                    summary.down_votes += 1
                    if not created:
                        summary.up_votes -= 1

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

