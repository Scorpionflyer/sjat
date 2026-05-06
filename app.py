import requests
import pandas as pd
from io import StringIO
import json
import geopandas as gpd
import matplotlib.pyplot as plt

STATISTIKAAMETI_API_URL = "https://andmed.stat.ee/api/v1/et/stat/RV032"

JSON_PAYLOAD_STR =""" {
  "query": [
    {
      "code": "Aasta",
      "selection": {
        "filter": "item",
        "values": [
          "2014",
          "2015",
          "2016",
          "2017",
          "2018",
          "2019",
          "2020",
          "2021",
          "2022",
          "2023"
        ]
      }
    },
    {
      "code": "Maakond",
      "selection": {
        "filter": "item",
        "values": [
          "39",
          "44",
          "49",
          "51",
          "57",
          "59",
          "65",
          "67",
          "70",
          "74",
          "78",
          "82",
          "84",
          "86",
          "37"
        ]
      }
    },
    {
      "code": "Sugu",
      "selection": {
        "filter": "item",
        "values": [
          "2",
          "3"
        ]
      }
    }
  ],
  "response": {
    "format": "csv"
  }
}
"""
geojson = "maakonnad.geojson"

def import_data():
    headers = {
        'Content-Type': 'application/json'
    }
    parsed_payload = json.loads(JSON_PAYLOAD_STR)
    response = requests.post(STATISTIKAAMETI_API_URL, json=parsed_payload, headers=headers)
    if response.status_code == 200:
        print("Request successful.")
        text = response.content.decode('utf-8-sig')
        df = pd.read_csv(StringIO(text))
    else:
        print(f"Failed with status code: {response.status_code}")
        print(response.text)
    return df

def import_geojson():
    gdf = gpd.read_file(geojson)
    return gdf

def get_data_for_year(df, year):
    year_data = df[df.Aasta==year]
    return year_data

def plot(df):
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    df.plot(column='Loomulik iive',
                     ax=ax,
                     legend=True,
                     cmap='viridis',
                     legend_kwds={'label': "Loomulik iive"})
    plt.title('Loomulik iive maakonniti')
    plt.axis('off')
    plt.tight_layout()
    plt.show()
