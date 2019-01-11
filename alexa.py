#from __future__ import print_function
import requests # pylint: disable=E0401
import json
import configparser

import time

import logging

#
# speech synthesis https://developer.amazon.com/docs/custom-skills/speech-synthesis-markup-language-ssml-reference.html
#

logger = logging.getLogger()
logger.setLevel(logging.INFO)
#logging.basicConfig(format='%(asctime)s %(message)s',level=logging.DEBUG)

#
# Read in config from file
#
config = configparser.ConfigParser()
try:
    config.read('config.ini')
except Exception as e:
    logger.error('Cannot read the config.ini')

APP_TITLE = config['DEFAULT']['APP_TITLE']
WU_DATA_AGE = config['DEFAULT']['WU_DATA_AGE'] # seconds before checking WU API

my_alexa_skill_id = config['DEFAULT']['my_alexa_skill_id']

wu_station_id = config['DEFAULT']['wu_station_id']
wu_unit = config['DEFAULT']['wu_unit']
wu_version = config['DEFAULT']['wu_version']
wu_format = config['DEFAULT']['wu_format']

# Lambda calls this 
def handler(event, context):

    # all print() ends up in the CloudWatch logs - 5GB free
    logger.info('******** ' + APP_TITLE + ' Lambda Alexa Skill running ********')
    logger.info('Event: '+json.dumps(event))
    logger.info('remote appId '+event['session']['application']['applicationId'])

    # make sure only our skill calls this function
    incoming_appid = event['session']['application']['applicationId']
    if (incoming_appid != my_alexa_skill_id):
        raise ValueError("WARNING: Invalid Application ID: "+incoming_appid+' !='+my_alexa_skill_id)

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']}, event['session'])

    # event request type - what has alexa sent this function
    ert = event['request']['type']

    if ert == "LaunchRequest":
        return on_launch(event['request'], event['session'])

    elif ert == "IntentRequest":
        return on_intent(event['request'], event['session'])

    elif ert == "SessionEndedRequest":
        return on_session_ended(event['request'], event['session'])

    else:
        logger.error('unknown request type: '+ert)


def on_session_started(session_started_request, session):
    """ Called when the session starts """

    logger.info("on_session_started requestId=" + session_started_request['requestId']
          + ", sessionId=" + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they want
    """

    logger.info("on_launch requestId=" + launch_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """

    logger.info("on_intent requestId=" + intent_request['requestId'] + ", sessionId=" + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    #
    # Dispatch to your Alexa skill's intent handlers
    #

    # weather skills
    if intent_name in ['getRain', 'getTemperature', 'getWind', 'getDetails']:
        return intent_getweather(intent, session)

    # base Alexa skills
    elif intent_name == "AMAZON.HelpIntent":    # what to say once the skill starts for the first time
        return get_welcome_response()

    elif intent_name == "AMAZON.StopIntent": # when the user says 'stop/exit/quit'
        return stop_intent()

    elif intent_name == "AMAZON.CancelIntent": # when the user says 'cancel'
        return stop_intent()

    elif intent_name == "AMAZON.FallbackIntent": # what happens if Alexa didnt understand what was said
        return fallback_intent()
    else:
        logger.error('Invalid Intent: '+str(intent))
        raise ValueError("Invalid intent") # if you get here, then you need to code more intents, check your logs


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """

    logger.info("on_session_ended requestId=" + session_ended_request['requestId'] +
          ", sessionId=" + session['sessionId'])
    # add cleanup logic here

# --------------- Functions that control the skill's behavior ------------------


def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """
    logger.info('welcome response')

    session_attributes = {}
    card_title = "Welcome"
    speech_output = APP_TITLE + " started." 
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    reprompt_text = "Please tell me the command I should send to your system"
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def fallback_intent():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """
    logger.info('fallback intent')

    session_attributes = {}
    card_title = "Opps"
    speech_output = "Sorry " + APP_TITLE + " did not understand that.  Please try again."
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    reprompt_text = "Please tell me the command I should send to your system"
    should_end_session = False
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))

def stop_intent():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """
    logger.info('stop intent')

    session_attributes = {}
    card_title = "Bye"
    speech_output = "Goodbye." 

    reprompt_text = ""
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


#######################################################################
#  Weather Functions

def degToCompass(num):
    val=int((num/22.5)+.5)
    long_cardinals = {'N':'North', 'S':'South', 'E':'East', 'W':'West'}
    cardinals=["N","NNE","NE","ENE","E","ESE", "SE", "SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    direction = cardinals[(val % 16)]
    arrCards = list(direction)

    # create word based direction to Allow Alexa to speak it
    longDirection = ''
    for aC in arrCards:
        longDirection += ' ' + long_cardinals[aC]

    return longDirection


def get_weather_data():
    """ 
    Download current weather report from Weather Underground API 
    """

    logger.info('get weather data')
    r = requests.get("https://stationdata.wunderground.com/cgi-bin/stationlookup?"+
        "station="+wu_station_id+
        "&units="+wu_unit+
        "&v="+wu_version+
        "&format="+wu_format
        )

    if r.status_code != 200:
        logger.error('wu status code:' +str(r.status_code))
        logger.error('wu text: '+str(r.text))
        raise ValueError("WU API returned non-200 code")

    wu = r.json()    

    wus = wu['stations'][wu_station_id]
    logger.info(json.dumps(wus)) # dump to logs incase it changes or we get errors
    return wus

def KMHtoMPH(kmh):
    return round(0.6214 * kmh)

def intent_getweather(intent, session):
    """ do the weather commands/actions
    """

    weather_action = intent['name']
    card_title = weather_action # for display gui

    logger.info('Weather Action: '+weather_action)

    should_end_session = False

    # check if we already have the WU data, if not get it
    session_attributes = session.get('attributes', {})
    if 'wus' not in session_attributes:
        logger.info('need wu data')
        wus = get_weather_data()
        session_attributes['wus'] = wus
    else:
        logger.info('use session attributes')
        wus = session_attributes['wus']
        updated = wus['updated']# last update timestamp

        # is data too old, then get it again
        last_updated = time.time() - updated
        logger.info('last update: '+str(last_updated))
        if last_updated > WU_DATA_AGE:
            wus = get_weather_data()
            session_attributes['wus'] = wus

    # data we want
    temperature = round(wus['temperature'])
    wind_dir = wus['wind_dir_degrees']
    wind_speed = wus['wind_speed'] # km/h
    wind_gust_speed = wus['wind_gust_speed']
    humidity = wus['humidity']
    rain_rate = wus['precip_rate'] # mm/h
    rain_today = wus['precip_today'] # mm
    pressure = wus['pressure']
    dewpoint = wus['dewpoint']
    windchill = round(wus['windchill'])

    reprompt_text = "I didn't quite understand that, please try again..."
  
    if weather_action == 'getTemperature':
        speech_output = "The outside temperature is " +  str(temperature) + " degrees C. " 

            #" Humidity is " + str(humidity) + " percent." 
        
        if 'windchill' in wus:
            if windchill != temperature:  
                speech_output = speech_output + \
                "But the windchill drops the temperature to " + str(windchill) + " degrees C."

    elif weather_action == 'getRain':
        speech_output = "There has been " + \
            str(rain_today) + " mm of rain today."

        if rain_rate > 0:
            speech_output = speech_output + \
                " and it is currently raining at a rate of " + \
                str(rain_rate) + " mm per hour."  

    elif weather_action == 'getWind':
        if wind_speed == 0:
            speech_output = "It's not windy at the moment."
        else:
            speech_output = "The wind speed is currently " + \
                str(KMHtoMPH(wind_speed)) + " mph, " + \
                " from the " + degToCompass(wind_dir) + ",  " + \
                " with gusts of " + str(KMHtoMPH(wind_gust_speed)) + " mph."

    elif weather_action == 'getDetails':
        speech_output = "No details yet." 

    else:
        speech_output = APP_TITLE + " did not understand that. Please try again."
        reprompt_text = "Please tell me the command I should send to your " + APP_TITLE +  "system"

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


# --------------- Helpers that build all of the responses ----------------------


def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': 'SessionSpeechlet - ' + title,
            'content': 'SessionSpeechlet - ' + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }




def build_response(session_attributes, speechlet_response):
    response = {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }
    logger.info('SAY: '+response['response']['outputSpeech']['text'])
    return response

