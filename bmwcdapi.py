#! /usr/bin/env python3
#
# **** bmwcdapi.py ****
# https://github.com/jupe76/bmwcdapi
#
# Query vehicle data from the BMW ConnectedDrive Website, i.e. for BMW i3
# Based on the excellent work by Sergej Mueller
# https://github.com/sergejmueller/battery.ebiene.de
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import json
import requests
import time
import datetime
import urllib.parse
import re
import argparse
import xml.etree.ElementTree as etree

# ADJUST HERE if OH is not running on "localhost:8080"
OPENHABIP = "localhost:8080"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0"

class ConnectedDrive(object):

    def __init__(self):
        #REST_OF_WORLD: 'b2vapi.bmwgroup.com'
        #NORTH_AMERICA:'b2vapi.bmwgroup.us'
        #CHINA: 'b2vapi.bmwgroup.cn:8592'
        servers = {'1': 'customer.bmwgroup.com',
                '2': 'b2vapi.bmwgroup.us',
                '3': 'b2vapi.bmwgroup.cn:8592'}
        try:
            region = self.ohGetValue("Bmw_Region").json()["label"]
        except:
            #fallback if no region is defined
            region = '1'

        try:
            self.serverUrl = servers[region]
        except:
            #fallback for nonexisting region
            self.serverUrl = servers['1']

        self.authApi = 'https://' + self.serverUrl +'/gcdm/oauth/authenticate'
        self.vehicleApi = 'https://myc-profile.bmwgroup.com'

        self.printall = False
        self.bmwUsername = self.ohGetValue("Bmw_Username").json()["label"]
        self.bmwPassword = self.ohGetValue("Bmw_Password").json()["label"]
        self.bmwVin = self.ohGetValue('Bmw_Vin').json()["label"].upper()
        self.accessToken = self.ohGetValue('Bmw_accessToken').json()["state"]
        self.tokenExpires = self.ohGetValue('Bmw_tokenExpires').json()["state"]

        #print('self.tokenExpires ' + self.tokenExpires)
        try:
            if (datetime.datetime.now() >= datetime.datetime.strptime(self.tokenExpires,"%Y-%m-%d %H:%M:%S.%f")):
                newTokenNeeded = True
            else:
                newTokenNeeded = False
        except:
            self.tokenExpires = 'NULL'
            newTokenNeeded = True

        if((self.tokenExpires == 'NULL') or (newTokenNeeded == True)):
            self.generateCredentials()
        else:
            self.authenticated = True

    def generateCredentials(self):
        """
        If previous token has expired, create a new one.
        New method to get oauth token from bimmer_connected lib
        """

        headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": "124",
                "Connection": "Keep-Alive",
                "Host": self.serverUrl,
                "Accept-Encoding": "gzip",
                "Authorization": "Basic blF2NkNxdHhKdVhXUDc0eGYzQ0p3VUVQOjF6REh4NnVuNGNEanli"
                                 "TEVOTjNreWZ1bVgya0VZaWdXUGNRcGR2RFJwSUJrN3JPSg==",
                "Credentials": "nQv6CqtxJuXWP74xf3CJwUEP:1zDHx6un4cDjybLENN3kyfumX2kEYigWPcQpdvDRpIBk7rOJ",
                "User-Agent": "okhttp/2.60",
        }

        values = {
            'grant_type': 'password',
            'scope': 'authenticate_user vehicle_data remote_services',
            'username': self.bmwUsername,
            'password': self.bmwPassword,
        }

        data = urllib.parse.urlencode(values)
        url = self.authApi.format(server=self.serverUrl)
        r = requests.post(url, data=data, headers=headers,allow_redirects=False)
        if (r.status_code != 200):
            self.authenticated = False
            return
        myPayLoad=r.json()

        self.accessToken=myPayLoad['access_token']
        self.ohPutValue('Bmw_accessToken',self.accessToken)

        expirationSecs=myPayLoad['expires_in']
        self.tokenExpires = datetime.datetime.now() + datetime.timedelta(seconds=expirationSecs)
        self.ohPutValue('Bmw_tokenExpires',self.tokenExpires)

        self.authenticated = True
        return

    def ohPutValue(self, item, value):
        rc =requests.put('http://' + OPENHABIP + '/rest/items/'+ item +'/state', str(value))
        if(rc.status_code != 202):
            print("Warning: couldn't save item " + item + " to openHAB")

    def ohGetValue(self, item):
        r = requests.get('http://' + OPENHABIP + '/rest/items/'+ item)
        if(r.status_code != 200):
            print("Status code ", r.status_code)
            print("Warning: couldn't get item " + item + " from openHAB")
        return r

    def queryData(self):
        headers = {
            "Content-Type": "application/json",
            "User-agent": USER_AGENT,
            "Authorization" : "Bearer "+ self.accessToken
            }

        r = requests.get(self.vehicleApi+'/dynamic/v1/'+self.bmwVin+'?offset=-60', headers=headers,allow_redirects=True)
        if (r.status_code != 200):
            return 70 #errno ECOMM, Communication error on send

        map=r.json() ['attributesMap']
        #optional print all values
        if(self.printall==True):
            for k, v in map.items():
                print(k, v)
        
        valueList = ['chargingLevelHv', 
                    'beRemainingRangeElectric',
                    'mileage',
                    'beRemainingRangeFuel',
                    'chargingSystemStatus',
                    'lastChargingEndResult',
                    'lastUpdateReason',
                    'unitOfLength']
        for val in valueList :
            if(val in map):
                self.ohPutValue("Bmw_"+ val,map[val])

        #these items were named differently than in ConnectedDrive 
        #so leave them for not breaking old configurations
        if('door_lock_state' in map):
            self.ohPutValue("Bmw_doorLockState",map['door_lock_state'])
        if('updateTime_converted_date' in map):
            self.ohPutValue("Bmw_updateTimeConverted", map['updateTime_converted_date']+ " " + map['updateTime_converted_time'])
        if('remaining_fuel' in map):
            self.ohPutValue("Bmw_remainingFuel", map['remaining_fuel'])
        if(('gps_lat' in map) and ('gps_lng' in map)):
            self.ohPutValue("Bmw_gpsLat", map['gps_lat'])
            self.ohPutValue("Bmw_gpsLng", map['gps_lng'])
            #maybe a combined value is more useful
            self.ohPutValue("Bmw_gpsLatLng", (map['gps_lat']+ "," + map['gps_lng']))
        if('soc_hv_percent' in map):
            self.ohPutValue("Bmw_socHvPercent",map['soc_hv_percent'])


        r = requests.get(self.vehicleApi+'/navigation/v1/'+self.bmwVin, headers=headers,allow_redirects=True)
        if (r.status_code != 200):
            return 70 #errno ECOMM, Communication error on send

        map=r.json()
        #optional print all values
        if(self.printall==True):
            for k, v in map.items():
                print(k, v)

        if('socmax' in map):
            self.ohPutValue("Bmw_socMax",map['socmax'])

        r = requests.get(self.vehicleApi+'/efficiency/v1/'+self.bmwVin, headers=headers,allow_redirects=True)
        if (r.status_code != 200):
            return 70 #errno ECOMM, Communication error on send
        if(self.printall==True):
            for k, v in r.json().items():
                print(k, v)

        #lastTripList
        myList=r.json() ["lastTripList"]
        for listItem in myList:
            if (listItem["name"] == "LASTTRIP_DELTA_KM"):
                pass
            elif (listItem["name"] == "ACTUAL_DISTANCE_WITHOUT_CHARGING"):
                pass
            elif (listItem["name"] == "AVERAGE_ELECTRIC_CONSUMPTION"):
                self.ohPutValue("Bmw_lastTripAvgConsum", listItem["lastTrip"])
            elif (listItem["name"] == "AVERAGE_RECUPERATED_ENERGY_PER_100_KM"):
                self.ohPutValue("Bmw_lastTripAvgRecup", listItem["lastTrip"])
            elif (listItem["name"] == "CUMULATED_ELECTRIC_DRIVEN_DISTANCE"):
                pass

        return 0 # ok

    def executeService(self,service):
        # lock doors:     RDL
        # unlock doors:   RDU
        # light signal:   RLF
        # sound horn:     RHB
        # climate:        RCN

        #https://www.bmw-connecteddrive.de/api/vehicle/remoteservices/v1/WBYxxxxxxxx123456/history

        # query execution status retries and interval time
        MAX_RETRIES = 9
        INTERVAL = 10 #secs

        print("executing service " + service)

        serviceCodes ={
            'climate' : 'RCN', 
            'lock': 'RDL', 
            'unlock' : 'RDU',
            'light' : 'RLF',
            'horn': 'RHB'}

        command = serviceCodes[service]
        headers = {
            "Content-Type": "application/json",
            "User-agent": USER_AGENT,
            "Authorization" : "Bearer "+ self.accessToken
            }

        r = requests.post(self.vehicleApi+'/remoteservices/v1/'+self.bmwVin+'/'+command, headers=headers,allow_redirects=True)
        if (r.status_code!= 200):
            return 70 #errno ECOMM, Communication error on send

        #<remoteServiceStatus>DELIVERED_TO_VEHICLE</remoteServiceStatus>
        #<remoteServiceStatus>EXECUTED</remoteServiceStatus>
        #wait max. ((MAX_RETRIES +1) * INTERVAL) = 90 secs for execution 
        for i in range(MAX_RETRIES):
            time.sleep(INTERVAL)
            r = requests.get(self.vehicleApi+'/remoteservices/v1/'+self.bmwVin+'/state/execution', headers=headers,allow_redirects=True)
            #print("status execstate " + str(r.status_code) + " " + r.text)
            root = etree.fromstring(r.text)
            remoteServiceStatus = root.find('remoteServiceStatus').text
            #print(remoteServiceStatus)
            if(remoteServiceStatus=='EXECUTED'):
                break

        if(remoteServiceStatus!='EXECUTED'):
            return 62 #errno ETIME, Timer expired

        return 0 # ok

    def sendMessage(self,message):
        # Endpoint: https://www.bmw-connecteddrive.de/api/vehicle/myinfo/v1
        # Type: POST
        # Body:
        # {
        #   "vins": ["<VINNUMBER>"],
        #   "message": "CONTENT",
        #   "subject": "SUBJECT"
        # }

        headers = {
            "Content-Type": "application/json",
            "User-agent": USER_AGENT,
            "Authorization" : "Bearer "+ self.accessToken
            }

        values = {'vins' : [self.bmwVin],
                    'message' : message[1],
                    'subject' : message[0]
                    }
        r = requests.post(self.vehicleApi+'/myinfo/v1', data=json.dumps(values), headers=headers,allow_redirects=True)
        if (r.status_code!= 200):
            return 70 #errno ECOMM, Communication error on send

        return 0

def main():
    print("...running bmwcdapi.py")
    c = ConnectedDrive()

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--printall', action='store_true',
        help='print all values that were received')
    parser.add_argument('-e', '--execservice', dest='service', 
        choices=['climate', 'lock', 'unlock', 'light', 'horn'], 
        action='store', help='execute service like instant climate control')
    parser.add_argument('-s', '--sendmesg', nargs=2, dest='message',
        metavar=('subject','message'),
        action='store', help='send a message to the car')

    args = vars(parser.parse_args())

    if(args["printall"]==True):
        c.printall=True

    # dont query data and execute the service at the same time, takes too long
    if(args["service"] and c.authenticated == True):
        # execute service
        execStatusCode = c.executeService(args["service"])
    elif(args["message"] and c.authenticated == True):
        # snd message
        execStatusCode = c.sendMessage(args["message"])
    elif(c.authenticated == True):
        # else, query data
        execStatusCode = c.queryData()
    elif(c.authenticated == False):
        print("could not authenticate, user or password wrong?")
        #errno EACCES 13 Permission denied
        execStatusCode = 13
        
    #print("execStatusCode="+ str(execStatusCode) )
    return execStatusCode

if __name__ == '__main__':
    main()
