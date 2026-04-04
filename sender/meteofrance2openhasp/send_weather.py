from typing import Optional

from meteofrance_api import MeteoFranceClient
from datetime import datetime, timezone, UTC
import json
import paho.mqtt.client as mqtt
import sys
import logging
from typing import Any

# max value in mm rain that is the top in the rain graph
MAX_RAIN = 8.0

# changing the following variables will require a thorough screen redesign
NR_RAINSECTIONS = 6
NR_HOURS_ON_MAIN_PAGE = 8
NR_DAYS_IN_OVERVIEW = 8

# this is tested and compatible with the following versions:

# Python 3.11 ... 3.14
# paho-mqtt 2.1.0
# meteofrance-api 1.0.2 ... 1.5.0

# Send weather info to an openHASP plate. To be called every X minutes.
# It will replace all weather data on each pass.

# The weather info will be shown on the following pages:
# * main page: weather now, overal today, overall tomorrow, rain in next hour, and weather for the next 8 hours
# * week overview page: overall info for the next 8 days
# * N pages, 1 per day, each with quarter-day overview (N = configurable via NR_DAYS_DETAIL)

# The pages must be consecutive, and in that order. The start page = configurable via start_page.

# This code requires one to have set the time zone of the machine to the time zone of the to-be-displayed data.
# (It won't be difficult to change that --see timestamp_to_locale_time--, it's just not done --yet)

# The code could be a bit more robust against network and meteofrance API problems (that happens),
# but since the data is replaced fully every X minutes, doing that is lower priority.


# helper functions:

def weekday_name_fr(nr: int, short: bool) -> str:
    """get the French week day name.
    Using this allows me to not require the installation of a specific locale.

    Args:
        nr (int): 0 - 6, 0 = sunday
        short (bool): True for short name

    Returns:
        str: weekday name in french
    """
    longnames = ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
    shortnames = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    
    if nr is None or nr < 0 or nr > 6:
        return "???"
    if short:
        return shortnames[nr]
    else:
        return longnames[nr]


def datediff_fr(nr: int) -> str:
    """ get the french name for the difference in days

    Args:
        nr (int): days from now

    Returns:
        str: date difference name
    """
    if nr < -1:
        return "??"
    elif nr == -1:
        return "Hier"
    elif nr == 0:
        return "Aujourd'hui"
    elif nr == 1:
        return "Demain"
    elif nr == 2:
        return "Après demain"
    else:
        return f"Dans {nr} jours"


class MeteoFrance2OpenHasp:

    def __init__(self, mqtt_client: Optional[mqtt.Client]):
        self._plates = []
        self._city = "" 
        self._max_nr_days_detail = 0
        self._mqtt_client = mqtt_client

    def load_config(self, config: dict[str, Any]) -> bool:
        """ validate the configuration and load the main variables from the configuration into the class variables """        
        self._max_nr_days_detail = 0     
        self._plates = config.get("plates")   
        if not isinstance(self._plates, list):
            logging.error("Plates configuration must be a list.")
            return False
        for plate in self._plates:
            if not isinstance(plate.get("name"), str):
                logging.error("Each plate must have a name of type string.")
                return False
            if not isinstance(plate.get("start_page"), int):
                logging.error(f"Plate '{plate.get('name')}' must have an integer 'start_page'.")
                return False
            if not isinstance(plate.get("nr_days_detail"), int):
                logging.error(f"Plate '{plate.get('name')}' must have an integer 'nr_days_detail'.")
                return False
            if plate.get("nr_days_detail") > self._max_nr_days_detail:
                self._max_nr_days_detail = plate.get("nr_days_detail")

            if not isinstance(plate.get("extra_tempnow"), (str, type(None))):
                logging.error(f"Plate '{plate.get('name')}' has invalid 'extra_tempnow' (must be string or null).")
                return False
            if not isinstance(plate.get("extra_iconnow"), (str, type(None))):
                logging.error(f"Plate '{plate.get('name')}' has invalid 'extra_iconnow' (must be string or null).")
                return False
            
        self._city = config.get("city")            
        if not isinstance(self._city, str):
            logging.error("City must be a string.")
            return False
        return True

    def get_forecast(self, city: str = "Paris") -> dict:
        """ Get a simplified weather forecast.
        As the meteofrance-api library is aging a bit, this 
        function uses a mix of meteofrance-api and newer API calls. 

        Args:
            city (str, optional): City name. Defaults to "Paris".

        Returns:
            dict: weather forecast
        """
        try:
            # Init client
            client = MeteoFranceClient()
            now = int(datetime.now(timezone.utc).timestamp())

            # Search a location from name.
            list_places = client.search_places(city)
            my_place = list_places[0]

            # Fetch weather forecast for the location
            my_place_weather_forecast = client.get_forecast_for_place(my_place)
            # logging.info("************ Forecast (global)")
            # logging.info(json.dumps(my_place_weather_forecast.__dict__, indent=2))
            # logging.info("************ Forecast (by hour)")
            # now = int(datetime.now(timezone.utc).timestamp())
            # hf = my_place_weather_forecast.forecast
            # logging.info(json.dumps(hf, indent=2))
            # dt = hf[0]["dt"]
            # lt = my_place_weather_forecast.timestamp_to_locale_time(dt)
            # logging.info(f"now = {now}, dt[0] = {dt}, locale = {lt} or {lt.strftime('%HH')}")
            # logging.info("************ Daily Forecast (by day)")
            # hf = my_place_weather_forecast.daily_forecast
            # logging.info(json.dumps(hf, indent=2))
            # logging.info("************ Today Forecast (today only)")
            # hf = my_place_weather_forecast.today_forecast
            # logging.info(json.dumps(hf, indent=2))
            # logging.info("************ Current Forecast (now)")
            # hf = my_place_weather_forecast.current_forecast
            # logging.info(json.dumps(hf, indent=2))

            obj = {}

            # per day
            dfs = my_place_weather_forecast.daily_forecast 
            obj["days"] = []
            for i in range(0, len(dfs)):
                tf = dfs[i]
                wf = {}
                if tf["weather12H"] is not None and tf["T"]["min"] is not None:
                    ts = datetime.fromtimestamp(tf["dt"], UTC)
                    # avoid setlocale, just force french names
                    wf["wd"] = weekday_name_fr(int(ts.strftime("%w")), True)
                    wf["day"] = ts.strftime("%d")
                    wf["temp_min"] = tf["T"]["min"]
                    wf["temp_max"] = tf["T"]["max"]
                    wf["desc"] = tf["weather12H"]["desc"]
                    wf["icon"] = tf["weather12H"]["icon"]
                    try:
                        wf["precipitation"] = tf["precipitation"]["24h"]
                    except:
                        wf["precipitation"] = 0
                    obj["days"].append(wf)

            # now
            hf = my_place_weather_forecast.current_forecast
            wf = {}

            wf["temp"] = hf["T"]["value"]
            wf["desc"] = hf["weather"]["desc"]
            wf["icon"] = hf["weather"]["icon"]
            # rainNow = hf["rain"]["1h"]  # is rain in mm in the next hour
            obj["now"] = wf

            rainlist: list[Optional[float]] = [None] * NR_RAINSECTIONS
            # If rain in the hour forecast is available, get it.
            if my_place_weather_forecast.position["rain_product_available"] == 1:
                RAIN_API_V3 = True
                if RAIN_API_V3:
                    dtname = "time"
                    rain_intensity_name = "rain_intensity"                

                    # v3 rain API, is better than the stock version. This is a very rough implementation.
                    resp = client.session.request(
                        "get", "v3/rain", params={"lat": my_place.latitude, "lon": my_place.longitude, "lang": "fr", "formatDate": "timestamp"}
                    )
                    # yeah, I could also redefine Rain, but this is enough
                    # sort rf.forecast on timestamp
                    rflist = sorted(resp.json()["properties"]["forecast"], key=lambda d: d[dtname])                
                else:
                    dtname = "dt"
                    rain_intensity_name = "rain"                 

                    rf = client.get_rain(my_place.latitude, my_place.longitude)
                    # sort rf.forecast on timestamp
                    rflist = sorted(rf.forecast, key=lambda d: d[dtname])

                    # deprecated: get next rain date/time
                    # next_rain_dt = rf.next_rain_date_locale()
                    # if not next_rain_dt:
                    #     propval = "non"
                    # else:
                    #     propval = next_rain_dt.strftime("%H:%M")
                    # obj["now"]["rain"] = propval

                # logging.info("************ Rain forecast ")
                # logging.info(json.dumps(rflist, indent=2))

                for i in range(0, len(rflist)):
                    rfdet = rflist[i]
                    dt = rfdet[dtname]
                    rain_intensity: int = rfdet[rain_intensity_name]
                    if i < len(rflist) - 1:
                        duration = int((rflist[i + 1][dtname] - dt) / 60)
                    else:
                        duration = 10
                    difft = int(round((dt - now) / 60))
                    # logging.info(f"+{difft} minutes, for ({duration}): {rain_intensity}")
                    if difft <= -10:
                        continue
                    if difft < 0:
                        difft = 0
                    offset = int(difft / 10)
                    remainder = int(difft % 10)
                    if offset < len(rainlist):
                        mm: float = 0
                        if rain_intensity <= 1:
                            mm = 0
                        elif rain_intensity >= 4:
                            mm = MAX_RAIN
                        else:
                            mm = (MAX_RAIN / 3.0) * (rain_intensity - 1) 
                        # record in the slot
                        if rainlist[offset] is not None:
                            v = (mm + rainlist[offset]) / 2  # type: ignore
                        else:
                            v = mm
                        rainlist[offset] = v
                        # and add the remainder to the next slot
                        if (remainder + duration >= 15) and offset < (len(rainlist) - 1):
                            offset += 1
                            if rainlist[offset] is not None:
                                v = (mm + rainlist[offset]) / 2  # type: ignore
                            else:
                                v = mm
                            rainlist[offset] = v                        
                        # logging.info(f"{offset} -> {v}")

            # logging.info(rainlist)
            obj["rain"] = rainlist

            # hourly
            wf = {}
            idx = 1
            # sort hourly forecast on "dt"
            tf = sorted(my_place_weather_forecast.forecast, key=lambda d: d['dt'])
            # logging.info("************ Hourly forecast ")
            # logging.info(json.dumps(tf, indent=1))
            # logging.info("************ Hourly forecast ")
            for hf in tf:
                if idx > NR_HOURS_ON_MAIN_PAGE: 
                    continue
                dt = hf["dt"]
                # logging.info(f"now = {now}, dt = {dt}")
                if dt > now:
                    wfh = {}
                    lt = my_place_weather_forecast.timestamp_to_locale_time(dt)
                    wfh["h"] = lt.strftime('%-HH')
                    wfh["temp"] = hf["T"]["value"]
                    wfh["desc"] = hf["weather"]["desc"]
                    wfh["icon"] = hf["weather"]["icon"]
                    precipitation = False
                    try:
                        # logging.info(f"{wfh['h']}: rain = {hf['rain']['1h']}")
                        if hf["rain"]["1h"] != 0:
                            precipitation = True
                    except:
                        pass
                    try:
                        # logging.info(f"{wfh['h']}: snow = {hf['rain']['1h']}")
                        if hf["snow"]["1h"] != 0:
                            precipitation = True
                    except:
                        pass
                    wfh["precipitation"] = precipitation
                    wf[idx] = wfh
                    idx += 1

            obj["hourly"] = wf

            # detailed day forecast
            # v2 API, is better than the stock version. This is a very rough implementation.
            wf = {}
            resp = client.session.request(
                "get",
                "v2/forecast",
                params={
                    "lat": my_place.latitude,
                    "lon": my_place.longitude,
                    "lang": "fr",
                    "formatDate": "timestamp",
                    "instants": "morning,afternoon,evening,night",
                },
            )
            dfs = resp.json()["properties"]["forecast"]
            dfs = sorted(dfs, key=lambda d: d["time"])
            now_date = my_place_weather_forecast.timestamp_to_locale_time(now).date()
            for df in dfs:
                # get the day
                dt = df["time"]
                f_day = my_place_weather_forecast.timestamp_to_locale_time(dt)
                f_date = f_day.date()
                diffdate = (f_date - now_date).days
                # meteofrance counts the night as belonging to the previous day
                if f_day.hour < 6:
                    diffdate -= 1     

                if diffdate > self._max_nr_days_detail:
                    continue

                # get the moment of day
                # Don't really like this, as it is a load of "magic strings", but they are stable.
                # This is aligned with the screen sections.
                moment_day = df["moment_day"]
                md = 0
                if moment_day == "matin":
                    md = 0
                elif moment_day == "après-midi":
                    md = 1
                elif moment_day == "soirée":
                    md = 2
                elif moment_day == "nuit":
                    md = 3

                if diffdate not in wf:
                    wf[diffdate] = {}

                # wf[diffdate]["title"] = datediff_fr(diffdate)
                # weekday(): 0 = monday. I expect 1 = monday.
                wf[diffdate]["title"] = f"{datediff_fr(diffdate)}, {weekday_name_fr((now_date.weekday() + 1 + diffdate) % 7, False)}"

                wp = {}
                wp["temp"] = df["T"]
                wp["icon"] = df["weather_icon"]
                wp["desc"] = df["weather_description"] 
                # and for diagnostics:
                wp["part"] = moment_day
                wp["time"] = my_place_weather_forecast.timestamp_to_locale_time(dt).strftime("%d-%m %H:%M")
                wf[diffdate][md] = wp

            obj["partials"] = wf

            obj["ok"] = True
            return obj
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logging.error(f"Exception: {str(e)} at line {exc_tb.tb_lineno}")  # type: ignore
            return {"ok": False}

    def sendDataToHASP(
        self,
        d: dict,
        plate_name: str = "plate",
        start_page: int = 2,
        nr_detail_pages: int = 4,
        extra_tempnow: Optional[str] = None,
        extra_iconnow: Optional[str] = None,
    ) -> bool:
        """ send the data to a plate

        Args:
            d (dict): output from get_forecast()
            plate_name (str, optional): the plate name. Defaults to "plate".
            start_page (int, optional): the start page. Defaults to 2.
            nr_detail_pages (int, optional): the number of detail pages. Defaults to 4.
            extra_tempnow (str, optional): the element to which to replicate temp now. Defaults to None
            extra_iconnow (str, optional): the element to which to replicate weather icon now. Defaults to None

        Returns:
            bool: True when OK
        """

        def formatT(temp) -> str:
            """format temperature

            Args:
                temp: temperature

            Returns:
                str: temp formatted
            """
            try:
                t = round(float(temp), None)  # None as the last parameter returns an int. 
                # Do not use "0", as that may return "-0" as output.
                return f"{t}°"
            except:
                return "??"

        def sendProp(plate_name: str, el: str, prop: str, txt: str):
            """Send a property

            Args:
                plate_name (str): plate name
                el (str): element on screen (pXbY)
                prop (str): the property
                txt (str): text to send
            """
            if txt is None:
                txt = "[]"
            topic = f"hasp/{plate_name}/command/{el}.{prop}"
            if self._mqtt_client:
                logging.debug(f"{topic}: \"{txt}\"")
                mi = self._mqtt_client.publish(topic, txt)
                mi.wait_for_publish()  # this does not seem to block until all is gone!
            else:
                logging.info(f"{topic}: \"{txt}\"")

        def sendTxt(plate_name: str, el: str, txt: str):
            """ send text to a label
            
            Args:
                plate_name (str): plate name
                el (str): element on screen (pXbY)
                txt (str): text to send
            """
            if txt is None:
                txt = "??"
            topic = f"hasp/{plate_name}/command/{el}.text"
            if self._mqtt_client:
                logging.debug(f"{topic}: \"{txt}\"")
                mi = self._mqtt_client.publish(topic, txt)
                mi.wait_for_publish()  # this does not seem to block until all is gone!
            else:
                logging.info(f"{topic}: \"{txt}\"")

        def sendImg(plate_name: str, el: str, txt: str):
            """ send an image

            Args:
                plate_name (str): plate name
                el (str): element on screen (pXbY)
                txt (str): base name of the image
            """
            if txt is None:
                txt = "p3j"
            topic = f"hasp/{plate_name}/command/{el}.src"
            txt = f"L:/{txt}.bin"
            if self._mqtt_client:
                logging.debug(f"{topic}: \"{txt}\"")                
                mi = self._mqtt_client.publish(topic, txt)
                mi.wait_for_publish()  # this does not seem to block until all is gone!
            else:
                logging.info(f"{topic}: \"{txt}\"")

        try:
            # ##### main page ######
            # now
            try:
                wf = d["now"]
            except:
                wf = {"temp": None, "desc": "None", "icon": "p3j", "rain": None}

            sendImg(plate_name, f"p{start_page}b6", wf["icon"] + "_big")
            if extra_iconnow:
                sendImg(plate_name, extra_iconnow, wf["icon"] + "_big")

            sendTxt(plate_name, f"p{start_page}b7", formatT(wf["temp"]))
            if extra_tempnow:
                sendTxt(plate_name, extra_tempnow, formatT(wf["temp"]))

            sendTxt(plate_name, f"p{start_page}b8", wf["desc"])
            # sendTxt(plate_name, f"p{start_page}b31", wf["rain"])

            # today
            for t in [0, 1]:  # today, tomorrow
                try:
                    wf = d["days"][t]
                except:
                    wf = {"temp_min": None, "temp_max": None, "desc": "None", "icon": "p3j"}
                if t == 0:
                    base = 11
                else:
                    base = 21
                sendImg(plate_name, f"p{start_page}b{base}", wf["icon"])
                sendTxt(plate_name, f"p{start_page}b{base + 1}", formatT(wf["temp_min"]))
                sendTxt(plate_name, f"p{start_page}b{base + 3}", formatT(wf["temp_max"]))
                sendTxt(plate_name, f"p{start_page}b{base + 4}", wf["desc"])

            # rain
            rainBarheight = 26
            rainMax = MAX_RAIN
            hadRain = False
            wf = d["rain"]
            for i in range(0, NR_RAINSECTIONS):
                try:
                    if wf[i] is None:
                        rt = 0
                    else:
                        rt = float(wf[i])
                    if rt < 0:
                        r = 0
                    elif rt > rainMax:
                        r = rainBarheight
                    else:
                        r = int(round(rainBarheight * (rt / rainMax), 0))
                except Exception as e:
                    logging.error(f"Exception on rain data: {str(e)}")
                    r = 0
                sendProp(plate_name, f"p{start_page}b{35 + i}", "h", str(rainBarheight - r))
                if r > 0:
                    hadRain = True

            # hide the rain section if there was nothing to show
            sendProp(plate_name, f"p{start_page}b42", "hidden", str(hadRain))

            # hourly
            # draw icons + text and get min/max
            tMin = None
            tMax = None
            tArr = []
            for i in range(0, NR_HOURS_ON_MAIN_PAGE):
                try:
                    wf = d["hourly"][i + 1]
                except:
                    wf = {"h": "??H", "temp": None, "desc": None, "icon": None, "precipitation": False}
                base = 60 + (i * 3)
                sendTxt(plate_name, f"p{start_page}b{base}", wf["h"])
                sendImg(plate_name, f"p{start_page}b{base + 1}", wf["icon"])
                sendTxt(plate_name, f"p{start_page}b{base + 2}", formatT(wf["temp"]))
                sendProp(plate_name, f"p{start_page}b{base + 2}", "bg_color", "white")
                sendProp(plate_name, f"p{start_page}b{base + 2}", "bg_grad_dir", "1")
                sendProp(plate_name, f"p{start_page}b{base + 2}", "bg_grad_color", "#40FFFF")
                sendProp(plate_name, f"p{start_page}b{base + 2}", "bg_main_stop", "100")
                raining = wf["precipitation"]
                sendProp(plate_name, f"p{start_page}b{base + 2}", "bg_opa", "80" if raining else "0")

                try:
                    t = float(wf["temp"])
                    ti = int(round(t, 0))
                    # ti = t
                    if tMin is None:
                        tMin = ti
                    if tMax is None: 
                        tMax = ti
                    if ti < tMin:
                        tMin = ti
                    if ti > tMax:
                        tMax = ti
                    tArr.append(ti)
                except:
                    tArr.append(None)

            # temp graph
            # lowest temp to be shown at screenTL, and highest at screenTL - screenTRange
            screenTL = 280
            screenTRange = 15
            screenImageTLOffset = -25
            screenXLeft = 30
            screenXStep = 60
            scaleFactor = None
            if not (tMin is None or tMax is None):
                tempRange = tMax - tMin
                # make it minimum MIN_TEMPSCALE degrees scale
                MIN_TEMPSCALE = 2
                if tempRange < MIN_TEMPSCALE:
                    addMargin = (MIN_TEMPSCALE - tempRange) / 2
                    tMin -= addMargin
                    tMax += addMargin
                    tempRange = tMax - tMin
                if tempRange > 0:
                    scaleFactor = screenTRange / tempRange
                else:
                    scaleFactor = None

            # temp graph: place the icons at the right height, and determine the line graph points
            x = screenXLeft
            i = 0
            points = []
            for t in tArr:
                if t is None or scaleFactor is None:
                    v = screenTL - (screenTRange / 2)
                else:
                    v = screenTL - (scaleFactor * (t - tMin))
                y = int(round(v, 0))
                points.append([x, y])
                base = 60 + (i * 3)
                sendProp(plate_name, f"p{start_page}b{base + 1}", "y", str(y + screenImageTLOffset))
                x += screenXStep
                i += 1
            # the temp line graph
            sendProp(plate_name, f"p{start_page}b41", "points", str(points))

            # ##### week overview page ######
            tMin = None
            tMax = None
            # the icons and the texts
            for i in range(0, NR_DAYS_IN_OVERVIEW):
                try:
                    wf = d["days"][i]
                except:
                    wf = {"wd": "??", "day": "??", "temp_min": None, "temp_max": None, "desc": "None", "icon": "p3j", "precipitation": 0}
                base = 20 + (i * 10)
                sendTxt(plate_name, f"p{start_page + 1}b{base}", wf["wd"])
                sendTxt(plate_name, f"p{start_page + 1}b{base + 1}", wf["day"])
                sendImg(plate_name, f"p{start_page + 1}b{base + 2}", wf["icon"])
                sendTxt(plate_name, f"p{start_page + 1}b{base + 5}", formatT(wf["temp_min"]))
                sendTxt(plate_name, f"p{start_page + 1}b{base + 3}", formatT(wf["temp_max"]))
                try:
                    t = float(wf["temp_min"])
                    ti = int(round(t, 0))
                    # ti = t
                    if tMin is None:
                        tMin = ti
                    if tMax is None: 
                        tMax = ti
                    if ti < tMin:
                        tMin = ti
                    if ti > tMax:
                        tMax = ti
                except:
                    pass
                try:
                    t = float(wf["temp_max"])
                    ti = int(round(t, 0))
                    # ti = t
                    if tMin is None:
                        tMin = ti
                    if tMax is None: 
                        tMax = ti
                    if ti < tMin:
                        tMin = ti
                    if ti > tMax:
                        tMax = ti
                except:
                    pass
                    # now print temp graph

            # determine the bar graphs. highest temp to be shown at screenTL, and lowest at screenTL + screenTRange
            min_height = 1
            screenTL = 222
            screenTRange = 284 - 222 - min_height
            screenXLeft = 29
            screenXStep = 60
            scaleFactor = None
            if not (tMin is None or tMax is None):
                tempRange = tMax - tMin
                # make it minimum MIN_TEMPSCALE degrees scale
                MIN_TEMPSCALE = 1
                if tempRange < MIN_TEMPSCALE:
                    addMargin = (MIN_TEMPSCALE - tempRange) / 2
                    tMin -= addMargin
                    tMax += addMargin
                    tempRange = tMax - tMin
                if tempRange > 0:
                    scaleFactor = screenTRange / tempRange
                else:
                    scaleFactor = None

            # the bar graphs
            for i in range(0, NR_DAYS_IN_OVERVIEW):            
                temp_min = None
                temp_max = None
                if scaleFactor is not None:
                    try:
                        wf = d["days"][i]
                        temp_min = int(round(wf["temp_min"]))
                        temp_max = int(round(wf["temp_max"]))
                    except:
                        pass
                    if temp_min is None:
                        temp_min = tMin
                    if temp_max is None:
                        temp_max = tMax

                    y_max = int(round(screenTL + (scaleFactor * (tMax - temp_max)), 0))  # type: ignore
                    y_min = int(round(screenTL + (scaleFactor * (tMax - temp_min)), 0)) + min_height  # type: ignore
                else:
                    y_max = screenTL
                    y_min = screenTL + screenTRange + min_height
                base = 20 + (i * 10)
                x = screenXLeft + (i * screenXStep)
                arr = []
                arr.append([x, y_max])
                arr.append([x, y_min])
                sendProp(plate_name, f"p{start_page + 1}b{base + 6}", "points", str(arr))

            # ###### day detail pages ######
            # day partials
            if 0 not in d["partials"]:
                offset = 1 
            else:
                offset = 0
            for section in range(0, nr_detail_pages):
                p = start_page + 2 + section

                if (section + offset) not in d["partials"]:
                    wf = {}
                    sendTxt(plate_name, f"p{p}b{20}", "")
                else:
                    wf = d["partials"][section + offset]
                    sendTxt(plate_name, f"p{p}b{20}", wf['title'])

                # 4 sections per day
                # I do not replace the day part name, although I could. But I already compared and made sure it all goes in the correct section.
                for part in range(0, 4):
                    base = 30 + (part * 5)
                    if part not in wf:
                        sendProp(plate_name, f"p{p}b{base + 4}", "hidden", "0")
                    else:
                        sendProp(plate_name, f"p{p}b{base + 4}", "hidden", "1")
                        sendTxt(plate_name, f"p{p}b{base + 1}", formatT(wf[part]["temp"]))
                        sendImg(plate_name, f"p{p}b{base + 2}", wf[part]["icon"] + "_big")
                        sendTxt(plate_name, f"p{p}b{base + 3}", wf[part]["desc"])

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logging.error(f"Exception on sending: {str(e)} at line {exc_tb.tb_lineno}")  # type: ignore
            return False

        return True

    def publish_weather(self) -> bool:
        if not self._city:
            logging.error("City not configured")
            return False
        logging.info(f"Fetching weather data for city: {self._city}")
        r = self.get_forecast(self._city)
        if not self._mqtt_client:
            logging.info("************ outcome")
            logging.info(json.dumps(r, indent=1))
            return True
        else:
            retv = False
            if r["ok"]:
                retv = True
                if not self._plates:
                    logging.error("No plates configured")
                    return False
                for plate in self._plates:
                    logging.info(f"Sending weather data to plate {plate['name']}")
                    if not self.sendDataToHASP(r, plate["name"], plate["start_page"], plate["nr_days_detail"], plate["extra_tempnow"], plate["extra_iconnow"]):
                        retv = False
            if not retv:
                logging.error("Error sending data")
                return False
        return True
    
    def dispose(self):
        pass
