from django.core.management.base import NoArgsCommand
from django_votes import models


class Command(NoArgsCommand):
    help = 'Recalculate all the vote summaries'

    def handle_noargs(self, **options):
        for model_name in models._vote_models:
            print 'Updating: %s' % model_name
            m = models._vote_models[model_name]

            # Delete existing summaries
            m.objects.all().delete()

            # Regenerate summaries by querying every single item again
            for instance in m.get_owner_model().objects.all():
                instance.vote_summary
