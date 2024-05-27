from meteofrance_api import MeteoFranceClient
from datetime import datetime, timezone
import json
import paho.mqtt.client as mqtt
import time
import sys

# Send weather info to an openHASP plate. To be called every X minutes.
# It will replace all weather data on each pass.

# The weather info will be shown on the following pages:
# * main page: weather now, overal today, overall tomorrow, rain in next hour, and weather for the next 8 hours
# * week overview page: overall info for the next 8 days
# * N pages, 1 per day, each with quarter-day overview (N = configurable via NR_DAYS_DETAIL)

# The pages must be consecutive, and in that order. The start page = configurable via START_PAGE.

# This code requires one to have set the time zone of the machine to the time zone of the to-be-displayed data.
# (It won't be difficult to change that --see timestamp_to_locale_time--, it's just not done --yet)

# The code could be a bit more robust against network and meteofrance API problems (that happens),
# but since the data is replaced fully every X minutes, doing that is lower priority.

# the installation's specifics. Adapt this to your needs
MQTTSERVER = "192.168.4.20"
CITY = "Paris"
PLATE_NAME = "plate01"

# the page number for the main weather page
START_PAGE = 2
# changing the following variable will only require more or less pages
NR_DAYS_DETAIL = 4

# if DEBUGME is True, it will not send to MQTT, but will print on console.
DEBUGME = False  # True

# max value in mm rain that is the top in the rain graph
MAX_RAIN = 8.0

# changing the following variables will require a thorough screen redesign
NR_RAINSECTIONS = 6
NR_HOURS_ON_MAIN_PAGE = 8
NR_DAYS_IN_OVERVIEW = 8


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


def get_forecast(city: str = "Paris") -> dict:
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
        # print("************ Forecast (global)")
        # print(json.dumps(my_place_weather_forecast.__dict__, indent=2))
        # print("************ Forecast (by hour)")
        # now = int(datetime.now(timezone.utc).timestamp())
        # hf = my_place_weather_forecast.forecast
        # print(json.dumps(hf, indent=2))
        # dt = hf[0]["dt"]
        # lt = my_place_weather_forecast.timestamp_to_locale_time(dt)
        # print(f"now = {now}, dt[0] = {dt}, locale = {lt} or {lt.strftime('%HH')}")
        # print("************ Daily Forecast (by day)")
        # hf = my_place_weather_forecast.daily_forecast
        # print(json.dumps(hf, indent=2))
        # print("************ Today Forecast (today only)")
        # hf = my_place_weather_forecast.today_forecast
        # print(json.dumps(hf, indent=2))        
        # print("************ Current Forecast (now)")
        # hf = my_place_weather_forecast.current_forecast
        # print(json.dumps(hf, indent=2))
        
        obj = {}

        # per day
        dfs = my_place_weather_forecast.daily_forecast 
        obj["days"] = []
        for i in range(0, len(dfs)):
            tf = dfs[i]
            wf = {}
            if tf["weather12H"] is not None and tf["T"]["min"] is not None:
                ts = datetime.utcfromtimestamp(tf["dt"])
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
        
        rainlist = [None] * NR_RAINSECTIONS
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
                
            # print("************ Rain forecast ")
            # print(json.dumps(rflist, indent=2))
                          
            for i in range(0, len(rflist)):
                rfdet = rflist[i]
                dt = rfdet[dtname]
                rain_intensity = rfdet[rain_intensity_name]
                if i < len(rflist) - 1:
                    duration = int((rflist[i + 1][dtname] - dt) / 60)
                else:
                    duration = 10
                difft = int(round((dt - now) / 60))
                # print(f"+{difft} minutes, for ({duration}): {rain_intensity}")
                if difft <= -10:
                    continue
                if difft < 0:
                    difft = 0
                offset = int(difft / 10)
                remainder = int(difft % 10)
                if offset < len(rainlist):
                    mm = 0
                    if rain_intensity <= 1:
                        mm = 0
                    elif rain_intensity >= 4:
                        mm = MAX_RAIN
                    else:
                        mm = (MAX_RAIN / 3.0) * (rain_intensity - 1) 
                    # record in the slot
                    if rainlist[offset] is not None:
                        v = (mm + rainlist[offset]) / 2
                    else:
                        v = mm
                    rainlist[offset] = v
                    # and add the remainder to the next slot
                    if (remainder + duration >= 15) and offset < (len(rainlist) - 1):
                        offset += 1
                        if rainlist[offset] is not None:
                            v = (mm + rainlist[offset]) / 2
                        else:
                            v = mm
                        rainlist[offset] = v                        
                    # print(f"{offset} -> {v}")
        
        # print(rainlist)
        obj["rain"] = rainlist
        
        # hourly
        wf = {}
        idx = 1
        # sort hourly forecast on "dt"
        tf = sorted(my_place_weather_forecast.forecast, key=lambda d: d['dt']) 
        for hf in tf:
            if idx > NR_HOURS_ON_MAIN_PAGE: 
                continue
            dt = hf["dt"]
            # print(f"now = {now}, dt = {dt}")
            if dt > now:
                wfh = {}
                lt = my_place_weather_forecast.timestamp_to_locale_time(dt)
                wfh["h"] = lt.strftime('%-HH')
                wfh["temp"] = hf["T"]["value"]
                wfh["desc"] = hf["weather"]["desc"]
                wfh["icon"] = hf["weather"]["icon"]
                
                wf[idx] = wfh
                idx += 1
        
        obj["hourly"] = wf
        
        # detailed day forecast
        # v2 API, is better than the stock version. This is a very rough implementation.
        wf = {}
        resp = client.session.request(
            "get", "v2/forecast", params={"lat": my_place.latitude, "lon": my_place.longitude, 
                                          "lang": "fr", "formatDate": "timestamp", 
                                          "instants": "morning,afternoon,evening,night"}
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

            if diffdate > NR_DAYS_DETAIL:
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
        print(f"Exception: {str(e)} at line {exc_tb.tb_lineno}")
        return {"ok": False}


def sendDataToHASP(d: dict, plate_name: str = "plate") -> bool:
    """ send the data to a plate

    Args:
        d (dict): output from get_forecast()
        plate_name (str, optional): the plate name. Defaults to "plate".

    Returns:
        bool: True when OK
    """

    def formatT(temp) -> str:
        """format temperatore

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
        if not DEBUGME:
            mi = mqttc.publish(topic, txt)
            mi.wait_for_publish()  # this does not seem to block until all is gone!
        else:
            print(f"{topic}: \"{txt}\"")
                
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
        if not DEBUGME:
            mi = mqttc.publish(topic, txt)
            mi.wait_for_publish()  # this does not seem to block until all is gone!
        else:
            print(f"{topic}: \"{txt}\"")
    
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
        if not DEBUGME:
            mi = mqttc.publish(topic, txt)
            mi.wait_for_publish()  # this does not seem to block until all is gone!
        else:
            print(f"{topic}: \"{txt}\"")

    if not DEBUGME:
        mqttc = mqtt.Client()
        try:
            # yes, hard coded port. Easy to change though if needed.
            mqttc.connect(MQTTSERVER, 1883, 60)
        except Exception as e:
            print(f"Exception on MQTT connect: {str(e)}")
            return False
    
    try:
        # ##### main page ###### 
        # now
        try:
            wf = d["now"]
        except:
            wf = {"temp": None, "desc": "None", "icon": "p3j", "rain": None}
        sendImg(plate_name, f"p{START_PAGE}b6", wf["icon"] + "_big")
        sendTxt(plate_name, f"p{START_PAGE}b7", formatT(wf["temp"]))
        sendTxt(plate_name, f"p{START_PAGE}b8", wf["desc"])
        # sendTxt(plate_name, f"p{START_PAGE}b31", wf["rain"])

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
            sendImg(plate_name, f"p{START_PAGE}b{base}", wf["icon"])
            sendTxt(plate_name, f"p{START_PAGE}b{base + 1}", formatT(wf["temp_min"]))
            sendTxt(plate_name, f"p{START_PAGE}b{base + 3}", formatT(wf["temp_max"]))
            sendTxt(plate_name, f"p{START_PAGE}b{base + 4}", wf["desc"])
            
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
                print(f"Exception on rain data: {str(e)}")
                r = 0
            sendProp(plate_name, f"p{START_PAGE}b{35 + i}", "h", rainBarheight - r)
            if r > 0:
                hadRain = True
                
        # hide the rain section if there was nothing to show
        sendProp(plate_name, f"p{START_PAGE}b42", "hidden", hadRain)
            
        # hourly
        # draw icons + text and get min/max
        tMin = None
        tMax = None
        tArr = []
        for i in range(0, NR_HOURS_ON_MAIN_PAGE):
            try:
                wf = d["hourly"][i + 1]
            except:
                wf = {"h": "??H", "temp": None, "desc": None, "icon": None}
            base = 60 + (i * 3)
            sendTxt(plate_name, f"p{START_PAGE}b{base}", wf["h"])
            sendImg(plate_name, f"p{START_PAGE}b{base + 1}", wf["icon"])
            sendTxt(plate_name, f"p{START_PAGE}b{base + 2}", formatT(wf["temp"]))
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
            sendProp(plate_name, f"p{START_PAGE}b{base + 1}", "y", y + screenImageTLOffset)
            x += screenXStep
            i += 1
        # the temp line graph
        sendProp(plate_name, f"p{START_PAGE}b41", "points", str(points))
        
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
            sendTxt(plate_name, f"p{START_PAGE + 1}b{base}", wf["wd"])
            sendTxt(plate_name, f"p{START_PAGE + 1}b{base + 1}", wf["day"])
            sendImg(plate_name, f"p{START_PAGE + 1}b{base + 2}", wf["icon"])
            sendTxt(plate_name, f"p{START_PAGE + 1}b{base + 5}", formatT(wf["temp_min"]))
            sendTxt(plate_name, f"p{START_PAGE + 1}b{base + 3}", formatT(wf["temp_max"]))
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
                    
                y_max = int(round(screenTL + (scaleFactor * (tMax - temp_max)), 0))
                y_min = int(round(screenTL + (scaleFactor * (tMax - temp_min)), 0)) + min_height
            else:
                y_max = screenTL
                y_min = screenTL + screenTRange + min_height
            base = 20 + (i * 10)
            x = screenXLeft + (i * screenXStep)
            arr = []
            arr.append([x, y_max])
            arr.append([x, y_min])
            sendProp(plate_name, f"p{START_PAGE + 1}b{base + 6}", "points", str(arr))

        # ###### day detail pages ######
        # day partials
        if 0 not in d["partials"]:
            offset = 1 
        else:
            offset = 0
        for section in range(0, NR_DAYS_DETAIL):
            p = START_PAGE + 2 + section
            
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
                    sendProp(plate_name, f"p{p}b{base+4}", "hidden", "0")
                else:
                    sendProp(plate_name, f"p{p}b{base+4}", "hidden", "1")
                    sendTxt(plate_name, f"p{p}b{base+1}", formatT(wf[part]["temp"]))
                    sendImg(plate_name, f"p{p}b{base+2}", wf[part]["icon"] + "_big")
                    sendTxt(plate_name, f"p{p}b{base+3}", wf[part]["desc"])
    
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print(f"Exception on sending: {str(e)} at line {exc_tb.tb_lineno}") 
        return False   
    
    if not DEBUGME:
        time.sleep(5)  # flush out the MQTT queue. It seems that wait_for_publish() does not work properly 
        mqttc.disconnect()
    
    return True


if __name__ == '__main__':
    
    r = get_forecast(CITY)
    if DEBUGME:
        print("************ outcome")
        print(json.dumps(r, indent=1))
    
    if r["ok"]:
        v = sendDataToHASP(r, PLATE_NAME)
        if v:
            exit(0)
    exit(1)
