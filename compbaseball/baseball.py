import json
import os

import pandas as pd

from paramtools.parameters import Parameters
from marshmallow import ValidationError

CURRENT_PATH = os.path.abspath(os.path.dirname(__file__))


class BaseballParams(Parameters):
    schema = os.path.join(CURRENT_PATH, "schema.json")
    defaults = os.path.join(CURRENT_PATH, "defaults.json")

    def post_validate(self, raise_errors=True):
        self.post_validate_pitcher(raise_errors=raise_errors)
        self.post_validate_batter(raise_errors=raise_errors)

    def post_validate_pitcher(self, raise_errors=True):
        with open(os.path.join(CURRENT_PATH, "playerchoices.json")) as f:
            choices = json.loads(f.read())
        pitcher = self.get("pitcher")[0]["value"]
        errors = []
        if pitcher not in choices["choices"]:
            errors = [f"ERROR: Pitcher \"{pitcher}\" not allowed."]
            ve = ValidationError({"pitcher": errors})
            if raise_errors:
                raise ve
            else:
                self.format_errors(ve)

    def post_validate_batter(self, raise_errors=True):
        with open(os.path.join(CURRENT_PATH, "playerchoices.json")) as f:
            choices = json.loads(f.read())
        batters = self.get("batter")[0]["value"]
        errors = []
        for batter in batters:
            if batter not in choices["choices"]:
                errors.append(f"ERROR: Batter \"{batter}\" not allowed.")
        if errors:
            ve = ValidationError({"batter": errors})
            if raise_errors:
                raise ve
            else:
                self.format_errors(ve)


def get_inputs(use_2018=True):
    params = BaseballParams()
    spec = params.specification(meta_data=True, use_2018=use_2018)
    return {"matchup": spec}


def parse_inputs(inputs, jsonparams, errors_warnings, use_2018=True):
    adjustments = inputs["matchup"]
    params = BaseballParams()
    params.adjust(adjustments, raise_errors=False)
    params.post_validate()
    errors_warnings["matchup"]["errors"].update(params.errors)
    return (inputs, {"matchup": json.dumps(inputs)}, errors_warnings)


def pdf_to_clean_html(pdf):
    """Takes a PDF and returns an HTML table without any deprecated tags or
    irrelevant styling"""
    return (pdf.to_html()
            .replace(' border="1"', '')
            .replace(' style="text-align: right;"', ''))


def get_matchup(use_2018, user_mods):
    adjustment = user_mods["matchup"]
    params = BaseballParams()
    params.adjust(adjustment)
    specs = params.specification(use_2018=use_2018)
    print("getting data according to: ", use_2018, specs)
    results = {'outputs': [], 'aggr_outputs': [], 'meta': {"task_times": [0]}}
    if use_2018:
        url = "https://s3.amazonaws.com/hank-statcast/statcast2018.parquet"
    else:
        url = "https://s3.amazonaws.com/hank-statcast/statcast.parquet"
    print(f"reading data from {url}")
    scall = pd.read_parquet(url, engine="pyarrow")
    print('data read')
    scall["date"] = pd.to_datetime(scall["game_date"])
    sc = scall.loc[(scall.date >= pd.Timestamp(specs["start_date"][0]["value"])) &
                   (scall.date < pd.Timestamp(specs["end_date"][0]["value"]))]
    del scall
    print('filtered by date')

    gb = sc.groupby(
        ["balls", "strikes"])
    agg_pitch_outcome_normalized = pd.DataFrame(gb["type"].value_counts(normalize=True))
    del gb

    gb = sc.groupby(
        ["balls", "strikes"])
    agg_pitch_type_normalized = pd.DataFrame(gb["pitch_type"].value_counts(normalize=True))
    del gb

    results['aggr_outputs'].append({
        'tags': {'attribute': 'pitch-outcome'},
        'title': 'Pitch outcome by count for all players',
        'downloadable': [{'filename': 'pitch_outcome.csv',
                          'text': agg_pitch_outcome_normalized.to_csv()}],
        'renderable': pdf_to_clean_html(agg_pitch_outcome_normalized)})
    results['aggr_outputs'].append({
        'tags': {'attribute': 'pitch-type'},
        'title': 'Pitch type by count for all players',
        'downloadable': [{'filename': 'pitch_type.csv',
                          'text': agg_pitch_type_normalized.to_csv()}],
        'renderable': pdf_to_clean_html(agg_pitch_type_normalized)})


    pitcher, batters = specs["pitcher"][0]["value"], specs["batter"][0]["value"]
    for batter in batters:
        print(pitcher, batter)
        pdf = sc.loc[(sc["player_name"]==pitcher) & (sc["batter_name"]==batter), :]
        if len(pdf) == 0:
            pitch_outcome_normalized = pd.DataFrame()
            pitch_outcome = pd.DataFrame()
            pitch_type_normalized = pd.DataFrame()
            pitch_type = pd.DataFrame()
        else:
            gb = pdf.loc[(pdf["player_name"]==pitcher) & (pdf["batter_name"]==batter), :].groupby(
                ["balls", "strikes"])
            pitch_outcome_normalized = pd.DataFrame(gb["type"].value_counts(normalize=True))
            pitch_outcome = pd.DataFrame(gb["type"].value_counts())
            del gb

            gb = pdf.loc[(pdf["player_name"]==pitcher) & (pdf["batter_name"]==batter), :].groupby(
                ["balls", "strikes"])
            pitch_type_normalized = pd.DataFrame(gb["pitch_type"].value_counts(normalize=True))
            pitch_type = pd.DataFrame(gb["pitch_type"].value_counts())
            del gb
            del pdf

        results["outputs"] += [
            {
                "dimension": batter,
                "tags": {"attribute": "pitch-outcome", "count": "normalized"},
                'title': f'Normalized pitch outcome by count for {pitcher} v. {batter}',
                'downloadable': [{'filename': f"normalized_pitch_outcome_{pitcher}_{batter}.csv",
                                "text": pitch_outcome_normalized.to_csv()}],
                'renderable': pdf_to_clean_html(pitch_outcome_normalized)
            },
            {
                "dimension": batter,
                "tags": {"attribute": "pitch-outcome", "count": "raw-count"},
                'title': f'Pitch outcome by count for {pitcher} v. {batter}',
                'downloadable': [{'filename': f"pitch_outcome_{pitcher}_{batter}.csv",
                                "text": pitch_outcome.to_csv()}],
                'renderable': pdf_to_clean_html(pitch_outcome)
            },
            {
                "dimension": batter,
                "tags": {"attribute": "pitch-type", "count": "normalized"},
                'title': f'Normalized pitch type by count for {pitcher} v. {batter}',
                'downloadable': [{'filename': f"normalized_pitch_type_{pitcher}_{batter}.csv",
                                "text": pitch_type_normalized.to_csv()}],
                'renderable': pdf_to_clean_html(pitch_type_normalized)
            },
            {
                "dimension": batter,
                "tags": {"attribute": "pitch-type", "count": "raw-count"},
                'title': f'Pitch type by count for {pitcher} v. {batter}',
                'downloadable': [{'filename': f"pitch_type{pitcher}_{batter}.csv",
                                "text": pitch_type.to_csv()}],
                'renderable': pdf_to_clean_html(pitch_type)
            },
        ]
    del sc
    return results
