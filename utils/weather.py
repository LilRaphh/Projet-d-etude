"""
utils/weather.py — Service météo centralisé
Remplace le code dupliqué dans app.py, routes/main.py et routes/stylist.py
"""
from typing import Optional, Tuple

import requests

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WMO = {
    0: "Ciel dégagé",
    1: "Principalement dégagé",
    2: "Partiellement nuageux",
    3: "Couvert",
    45: "Brouillard",
    48: "Brouillard givrant",
    51: "Bruine légère",
    53: "Bruine modérée",
    55: "Bruine forte",
    61: "Pluie légère",
    63: "Pluie modérée",
    65: "Pluie forte",
    71: "Neige légère",
    73: "Neige modérée",
    75: "Neige forte",
    80: "Averses légères",
    81: "Averses modérées",
    82: "Averses violentes",
    95: "Orage",
    96: "Orage avec grêle",
    99: "Orage violent",
}


def weather_icon(code: int) -> str:
    if code == 0:
        return "☀️"
    if code <= 2:
        return "🌤️"
    if code <= 3:
        return "☁️"
    if code <= 48:
        return "🌫️"
    if code <= 67:
        return "🌧️"
    if code <= 77:
        return "❄️"
    if code <= 82:
        return "🌦️"
    return "⛈️"


def _layer_advice(feels: int) -> str:
    if feels <= 0:
        return "Très froid — manteau, écharpe et gants indispensables"
    if feels <= 8:
        return "Froid — manteau et superpositions recommandés"
    if feels <= 14:
        return "Frais — veste légère ou pull conseillé"
    if feels <= 20:
        return "Doux — t-shirt + veste légère suffit"
    if feels <= 26:
        return "Chaud — tenue légère"
    return "Très chaud — matières légères et aérées"


def _geocode(city: str) -> Optional[dict]:
    try:
        resp = requests.get(
            GEO_URL,
            params={"name": city, "count": 1, "language": "fr", "format": "json"},
            timeout=6,
        )
        resp.raise_for_status()
        geo = resp.json()
        results = geo.get("results")
        return results[0] if results else None
    except (requests.Timeout, requests.ConnectionError, requests.RequestException, ValueError):
        return None


class WeatherService:
    @staticmethod
    def get_current(city: str) -> Optional[dict]:
        """Météo courante simplifiée (header global + page styliste)."""
        if not city:
            return None
        place = _geocode(city)
        if not place:
            return None
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                },
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})
            code = current.get("weather_code", 0)
            temp = round(current.get("temperature_2m", 0))
            feels = round(current.get("apparent_temperature", temp))
            wind = round(current.get("wind_speed_10m", 0))
            hum = round(current.get("relative_humidity_2m", 0))
            return {
                "city": place["name"],
                "temp": temp,
                "feels": feels,
                "wind": wind,
                "hum": hum,
                "code": code,
                "icon": weather_icon(code),
                "label": WMO.get(code, "Variable"),
                "desc": WMO.get(code, "Variable"),
                "layer": _layer_advice(feels),
            }
        except (requests.Timeout, requests.ConnectionError, requests.RequestException, ValueError):
            return None
        except Exception:
            return None

    @staticmethod
    def get_forecast(city: str) -> Tuple:
        """Prévisions complètes 7 jours + horaire (page /forecast)."""
        if not city:
            return None, "Aucune ville configurée."
        place = _geocode(city)
        if not place:
            return None, "Ville introuvable."
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
                    "hourly": "temperature_2m,weather_code,precipitation_probability,wind_speed_10m",
                    "forecast_days": 7,
                    "timezone": "auto",
                },
                timeout=6,
            )
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current", {})
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})
            code = current.get("weather_code", 0)

            current_view = {
                "city": place["name"],
                "temp": round(current.get("temperature_2m", 0)),
                "feels": round(current.get("apparent_temperature", 0)),
                "wind": round(current.get("wind_speed_10m", 0)),
                "hum": round(current.get("relative_humidity_2m", 0)),
                "code": code,
                "label": WMO.get(code, "Variable"),
                "icon": weather_icon(code),
            }

            days = []
            dates = daily.get("time", [])
            codes = daily.get("weather_code", [])
            tmax = daily.get("temperature_2m_max", [])
            tmin = daily.get("temperature_2m_min", [])
            rain_prob = daily.get("precipitation_probability_max", [])
            rain_sum = daily.get("precipitation_sum", [])
            wind_max = daily.get("wind_speed_10m_max", [])

            for i in range(len(dates)):
                c = codes[i]
                days.append({
                    "date": dates[i],
                    "code": c,
                    "label": WMO.get(c, "Variable"),
                    "icon": weather_icon(c),
                    "temp_max": round(tmax[i]) if tmax[i] is not None else None,
                    "temp_min": round(tmin[i]) if tmin[i] is not None else None,
                    "rain_prob": rain_prob[i],
                    "rain_sum": rain_sum[i],
                    "wind_max": round(wind_max[i]) if wind_max[i] is not None else None,
                })

            hours = []
            h_time = hourly.get("time", [])
            h_code = hourly.get("weather_code", [])
            h_temp = hourly.get("temperature_2m", [])
            h_rain = hourly.get("precipitation_probability", [])
            h_wind = hourly.get("wind_speed_10m", [])
            n = min(24, len(h_time), len(h_code), len(h_temp), len(h_rain), len(h_wind))
            for i in range(n):
                c = h_code[i]
                hours.append({
                    "time": h_time[i],
                    "temp": round(h_temp[i]) if h_temp[i] is not None else None,
                    "code": c,
                    "label": WMO.get(c, "Variable"),
                    "icon": weather_icon(c),
                    "rain_prob": h_rain[i],
                    "wind": round(h_wind[i]) if h_wind[i] is not None else None,
                })

            return {
                "place": {
                    "name": place.get("name"),
                    "latitude": place.get("latitude"),
                    "longitude": place.get("longitude"),
                    "country": place.get("country"),
                    "admin1": place.get("admin1"),
                },
                "current": current_view,
                "days": days,
                "hours": hours,
            }, None

        except requests.Timeout:
            return None, "Délai d'attente dépassé. Réessayez."
        except requests.ConnectionError:
            return None, "Impossible de contacter le service météo."
        except ValueError:
            return None, "Réponse météo invalide."
        except requests.RequestException as e:
            return None, f"Erreur réseau météo : {e}"
        except Exception:
            return None, "Impossible de récupérer les prévisions météo pour le moment."
