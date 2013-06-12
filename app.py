import gflags
import datetime
import json
# import config

from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import run
from flask import Flask, request, render_template, session, url_for, redirect, escape
from rfc3339 import rfc3339  # small library to format dates to rfc3339 strings (format for Google Calendar API requests)
from flask_oauth import OAuth

GOOGLE_CLIENT_ID = '524876334284.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '_yi1QfD2NJrKAX5u4cceFKj5'
REDIRECT_URI = '/authorized'
SECRET_KEY = 'development key'
DEBUG = True

app = Flask(__name__)
app.debug = DEBUG
app.secret_key = SECRET_KEY
# app.config.from_object(config)
FLAGS = gflags.FLAGS
oauth = OAuth()

google = oauth.remote_app('google',
    base_url='https://www.google.com/accounts/',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    request_token_url=None,
    request_token_params={'scope': 'https://www.googleapis.com/auth/calendar',
        'response_type': 'code'},
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_method='POST',
    access_token_params={'grant_type': 'authorization_code'},
    consumer_key=GOOGLE_CLIENT_ID,
    consumer_secret=GOOGLE_CLIENT_SECRET)


@app.route("/")
def index():
    access_token = session.get('access_token')
    if access_token is None:
        return redirect(url_for('login'))

    access_token = access_token[0]
    from urllib2 import Request, urlopen, URLError

    headers = {'Authorization': 'OAuth ' + access_token}
    req = Request('https://www.googleapis.com/calendar/v3/users/me/calendarList', None, headers)
    try:
        res = urlopen(req)
    except (URLError,), e:
        if e.code == 401 or e.code == 403:
            # Unauthorized - bad token
            session.pop('access_token', None)
            return redirect(url_for('login'))
        return str(e.code)
    response = res.read()
    calendar_list = json.loads(response)['items']
    return render_template('index.html', calendar_list=calendar_list)


@app.route("/login")
def login():
    callback = url_for('authorized', _external=True)
    return google.authorize(callback=callback)
    # print escape(session['token'])
    # return render_template('index.html')
    # page_token = None
    # if request.method == 'POST':
    #     return redirect(url_for('index'))
    # if request.method == 'GET':
    #     return google_oauth()
        # while True:
        #     service = google_oauth()
        #     calendar_list = service.calendarList().list(pageToken=page_token).execute()
        #     calendar_list_items = calendar_list['items']
        #     page_token = calendar_list.get('nextPageToken')
        #     if not page_token:
        #         break
        # return render_template("index.html", calendar_list=calendar_list_items)


# @app.route(REDIRECT_URI)
# @google.authorized_handler
# def authorized(resp):
#     access_token = resp['access_token']
#     session['access_token'] = access_token, ''
#     return redirect(url_for('index'))


# @google.tokengetter
# def get_access_token():
#     return session.get('access_token')


@app.route("/logout")
def logout():
    # remove the username from the session if it's there
    session.pop('username', None)
    return redirect(url_for('index'))


# function to turn date and time strings into date/time objects
# returns list with date and time objects
def strp_date_time(date, time):
    apptDate = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    apptTime = datetime.datetime.strptime(time, '%H:%M').time()
    return [apptDate, apptTime]


# function to turn strings of date and time into rfc3339 format for Google Calendar API call
# returns string of datetime in rfc339 format
def datetime_combine_rfc3339(date, time):
    combined = datetime.datetime.combine(date, time)
    rfc3339_datetime = rfc3339(combined)
    return rfc3339_datetime


# function to generate list of suggested free dates for user to choose from
def generate_date_list(startdate, enddate, starttime, endtime, calendarid, pagetoken):
    # strp_date_time returns list: [date object, time object]
    apptStartDateTime = strp_date_time(startdate, starttime)
    apptEndDateTime = strp_date_time(enddate, endtime)
    # td used to increment while loop one day at a time (24 hours)
    td = datetime.timedelta(hours=24)
    # store user's requested start time for use in while loop
    current_date = apptStartDateTime[0]
    # empty list to store suggested free dates
    free_dates = []
    # loop from user's requested start date to end date
    while current_date <= apptEndDateTime[0]:
        # format start and end times for Google Calendar API call
        start_rfc3339 = datetime_combine_rfc3339(current_date, apptStartDateTime[1])
        end_rfc3339 = datetime_combine_rfc3339(current_date, apptEndDateTime[1])
        # Google Calendar API call
        # returns a dictionary of calendar properties
        # one of the properties is a list of events that match the datetime criteria given
        service = google_oauth()
        events = service.events().list(calendarId=calendarid, pageToken=pagetoken, timeMax=end_rfc3339, timeMin=start_rfc3339).execute()
        # grab the list of events
        event_items = events.get('items')
        # if there are no events given back, then that time is empty
        # add date to the suggested free time list
        if not event_items:
            free_dates.append(current_date)
        current_date += td
    return free_dates


@app.route("/search_events", methods=['POST'])
def search_events():
    page_token = None
    while True:
        startdate = request.form['apptStartDate']
        starttime = request.form['apptStartTime']
        enddate = request.form['apptEndDate']
        endtime = request.form['apptEndTime']
        calendarid = request.form['calendarlist']

        free_dates = generate_date_list(startdate, enddate, starttime, endtime, calendarid, page_token)
        free_dates_string = []

        # TODO: add check to see if free_dates is empty (no free blocks in specified time period)

        for dates in free_dates:
            free_dates_string.append(dates.strftime("%Y-%m-%d"))

        if not page_token:
            break

    return render_template("suggestions.html", free_dates=free_dates_string, starttime=starttime, endtime=endtime, calendarid=calendarid)


@app.route("/schedule_event", methods=['POST'])
def schedule_event():
    # grab user inputs from the schedule_event form
    apptName = request.form['apptName']
    apptLocation = request.form['apptLocation']
    apptCalendarId = request.form['apptCalendarId']
    # from apptOptions, grab the start/end date and time user has chosen
    # apptOptions returns in format: 05/05/13, 12:00, 13:00
    # first, turn it into a list
    apptTime = request.form['apptOptions'].split()
    apptDate = apptTime[0]
    apptStartTime = apptTime[1]
    apptEndTime = apptTime[2]
    # convert datetime into rfc3339 format for Google API
    apptStartDateTime = strp_date_time(apptDate, apptStartTime)
    apptEndDateTime = strp_date_time(apptDate, apptEndTime)
    # format start and end times for Google Calendar API call
    start_rfc3339 = datetime_combine_rfc3339(apptStartDateTime[0], apptStartDateTime[1])
    end_rfc3339 = datetime_combine_rfc3339(apptEndDateTime[0], apptEndDateTime[1])
    event = {
      'summary': apptName,
      'location': apptLocation,
      'start': {
        'dateTime': start_rfc3339
      },
      'end': {
        'dateTime': end_rfc3339
      },
      # 'attendees': [
      #   {
      #     'email': 'attendeeEmail',
      #     # Other attendee's data...
      #   },
      #   # ...
      # ],
    }
    service = google_oauth
    created_event = service.events().insert(calendarId=apptCalendarId, body=event).execute()
    print created_event['id']
    return "Your appointment has been scheduled!"


if __name__ == "__main__":
    app.run(debug=True)
