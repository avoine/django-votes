from django_votes.models import _vote_models

def get_vote_model(model_name):
    if model_name in _vote_models:
        return _vote_models[model_name]
    else:
        raise Exception('No such vote model "%s"' % model_name)

def get_rating_model(model_name):
    if model_name in _rating_models:
        return _rating_models[model_name]
    else:
        raise Exception('No such rating model "%s"' % model_name)
