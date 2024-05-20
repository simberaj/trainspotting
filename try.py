import re
import io
import datetime
from html import escape, unescape
from html.parser import HTMLParser
from xml.etree import ElementTree

import requests

CHUNK_SIZE = 8096
TIME_FORMAT = "%H:%M"
PATH = "https://provoz.spravazeleznic.cz/tabule/Pages/StationTable.aspx"


class TimetableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.rows = []
        self.current_row = []
        self.cell_texts = []
        self.current_text = ""

    def handle_starttag(self, tag, attrs):
        if self.in_table:
            if self.in_row:
                if tag == "td":
                    self.in_cell = True
            if tag == "tr" and "tableTextRow" not in dict(attrs).get("class", ""):
                self.in_row = True
        elif tag == "tbody":
            self.in_table = True        

    def handle_data(self, text):
        if self.in_cell:
            self.current_text += text

    def handle_endtag(self, tag):
        if self.in_cell:
            if tag == "td":
                self.current_row.append(self.cell_texts)
                self.cell_texts = []
                self.in_cell = False
            elif self.current_text:
                self.cell_texts.append(self.current_text.strip())
                self.current_text = ""
        elif self.in_row:
            if tag == "tr":
                self.rows.append(self.current_row_record())
                self.current_row = []
                self.in_row = False
        elif self.in_table:
            if tag == "tbody":
                self.in_table = False

    def current_row_record(self):
        raise NotImplementedError


class ArrivalsParser(TimetableParser):
    def current_row_record(self):
        return {
            "from": self.current_row[0][0],
            "line": self.current_row[1][0],
            "arrival": self.current_row[4][0],
            "no": self.current_row[5][0],
            "carrier": self.current_row[5][1],
        }


class DeparturesParser(TimetableParser):
    def current_row_record(self):
        return {
            "departure": self.current_row[2][0],
            "no": self.current_row[3][0],
            "carrier": self.current_row[3][1],
            "line": self.current_row[4][0],
            "to": self.current_row[6][0],
        }


def parse(fp, parser):
    chunk = fp.read(CHUNK_SIZE)
    while chunk:
        parser.feed(chunk)
        chunk = fp.read(CHUNK_SIZE)
    return parser.rows


TRAIN_PATHS = [
    (3471, 3444),  # liben-hln
    (3471, 3449),  # liben-masa
    (3489, 3449),  # vysoc-masa
]


def process(train_paths):
    stations = {code for codes in train_paths for code in codes}
    arrivals, departures = load_arrivals_departures(stations)
    all_trains = match_trains(arrivals, departures, train_paths)
    return all_trains


def match_trains(arrivals, departures, paths):
    trains = []
    for s1, s2 in paths:
        trains.extend(match_departures_arrivals(
            departures.get(s1),
            arrivals.get(s2),
        ))
    trains.sort(key=lambda tr: tr["midtime"])
    return trains


def match_departures_arrivals(departures, arrivals):
    dep_dict = {dep["no"]: dep for dep in departures}
    for arr in arrivals:
        if arr["no"] in dep_dict:
            dep = dep_dict[arr["no"]]
            merged = arr.copy()
            merged["departure"] = dep["departure"]
            merged["to"] = dep["to"]
            dep_dt = datetime.datetime.strptime(dep["departure"], TIME_FORMAT)
            arr_dt = datetime.datetime.strptime(arr["arrival"], TIME_FORMAT)
            midtime = dep_dt + (arr_dt - dep_dt) / 2
            merged["midtime"] = midtime.strftime(TIME_FORMAT)
            yield merged


def load_arrivals_departures(stations):
    arrivals = {}
    departures = {}
    for station in stations:
        arr_f = requests.get(PATH, params={"Key": station, "Arr": 1})
        arrivals[station] = parse(io.StringIO(arr_f.text), ArrivalsParser())
        dep_f = requests.get(PATH, params={"Key": station})
        departures[station] = parse(io.StringIO(dep_f.text), DeparturesParser())
    return arrivals, departures


if __name__ == "__main__":
    for train in process():
        print(train)
