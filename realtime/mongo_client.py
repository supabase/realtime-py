from __future__ import annotations
from datetime import datetime 
from pymongo.collection import ReturnDocument
from twilio_client import Client as Twilio
import os
import pymongo

#TODO queries on nested object fields, project certain fields for results

class MongoServer():
    sms = Twilio()
    def __init__(self):
        MONGO_HOST = os.environ['MONGO_HOST']
        MONGO_PORT = int(os.environ['MONGO_PORT'])
        self.client = pymongo.MongoClient(MONGO_HOST, MONGO_PORT)
        #print('sanity check')
        self.alert_table = self.client['parse']['Alert']
#        self.alert_table = self.client['parse']['testAlerts']
        self.user_table = self.client['parse']['_User']
        self.sms_table = self.client['parse']['Sms']
        self.billing_plan_table = self.client['parse']['BillingPlan']
        self.discord_alerts_table = self.client['parse']['DiscordAlert']
        self.rarity_table = self.client['parse']['rarityRankings']


    def getAlertTable(self):
        return self.client['parse']['Alert']
#        return self.client['parse']['testAlerts']
        
    def getUserTable(self):
        return self.client['parse']['_User']

    def getSmsTable(self):
        return self.client['parse']['BillingPlan']

    def get_pending_discord_alerts(self):
        return [alert for alert in list(self.discord_alerts_table.find({'status': 1}))]

    def set_discord_alerts_delivered(self, alerts):
        for alert in alerts:
            self.discord_alerts_table.update_one({'_id': alert['_id']}, {'$set': {'status': 2}})

    def getActiveAlerts(self, slug):
        return list(self.alert_table.find({"status": 1, "collection": slug}))

    def getAllActiveAlerts(self):
        return list(self.alert_table.find({"status": 1}))
 
    def getCollectionsToListen(self):
        return list(set([alert['collection'] for alert in self.getAllActiveAlerts()]))
    
    def getTraitsToWatch(self,activeAlerts):
        return [alert['details']['trait'] for alert in activeAlerts if alert['type'] == 'traits']

    def hasHippoRole(self,username):
        user = self.user_table.find_one({"username": username})
        return user.get('billing_plan') == 'Hippo'

    def getRarityRank(self,slug,tokenID):
        rarityJson = self.rarity_table.find_one({"slug": slug})
        try:
            rarity = rarityJson["ranks"][str(int(tokenID))]
        except:
            rarity = 1000000
        return rarity

    def get_matching_trait_alerts(self, alerts, traits):
        matches = []
        for alert in alerts:
            for trait in traits['traits']:
                event_trait_type = trait['trait_type'].lower()
                event_trait_value = trait["value"].lower()
                alert_trait = alert["details"]["trait"].lower().split(".")
                alert_trait_type, alert_trait_value = alert_trait[0], alert_trait[1]
                if alert_trait_type == event_trait_type and event_trait_value == alert_trait_value:
                    matches.append(alert)
                    break
        return matches

    def cleanDuplicates(self, baseTriggers):
        toTrigger = []
        markTriggered = []
        skip = 0
        for trigger in baseTriggers:
            for alerts in toTrigger:
                if trigger["username"] in alerts["username"]:
                    if trigger["delivery_method"] in alerts["delivery_method"]:
                        if trigger["alert_type"] in alerts["alert_type"]:
                            if trigger["collection"] in alerts["collection"]:
                                markTriggered.append(trigger)
                                skip = 1
            if skip == 0:
                toTrigger.append(trigger)
            else:
                skip = 0
        return toTrigger, markTriggered    


    def getMatchingAlerts(self,alerts, tokenID, traits,EthPrice,rarity):
        baseToTrigger = []
        token_id_alerts = [alert for alert in alerts if alert['type'] == 'tokenId']
        baseToTrigger.extend([alert for alert in token_id_alerts if alert['details']['id'] == str(tokenID)])
        trait_alerts = [alert for alert in alerts if alert['type'] == 'traits']
        baseToTrigger.extend(self.get_matching_trait_alerts(trait_alerts, traits))
        price_alerts = [alert for alert in alerts if alert['type'] == 'price']
        baseToTrigger.extend([alert for alert in price_alerts if float(EthPrice) < float(alert['details']['price'])])
        rarity_alerts = [alert for alert in alerts if alert['type'] == 'rarity']
        baseToTrigger.extend([alert for alert in rarity_alerts if float(rarity) < float(alert['details']['rarity'])])

        return self.cleanDuplicates(baseToTrigger)
        

    def getMonthlySmsLimit(self,username):
        #for now only hippos allowed
        if self.hasHippoRole(username):
            hippo_plan = self.billing_plan_table.find_one({'name': 'Hippo'})
            return hippo_plan['smsLimit']
        else:
            return 0  

    def getSmsMTD(self,username):
        begMonth = datetime.strptime(datetime.today().strftime("%Y-%m"),"%Y-%m")  
        return self.sms_table.count_documents({"username": username, "createdAt": {'$gte': begMonth}})             

    def removeOverLimits(self, alerts):
        return [alert for alert in alerts if self.getSmsMTD(alert['username']) < self.getMonthlySmsLimit(alert['username'])]

    def removeNonMembers(self, alerts):
        return [alert for alert in alerts if self.hasHippoRole(alert['username'])]

    def getPhoneFromAlert(self,alert):
        user = self.user_table.find_one({"username": alert["username"]})
        return (str(user['countryCode'])+str(user['phoneNumber']))

    def updateAlertsDelivered(self,alert_list):
        alert_table = self.getAlertTable()
        for oldAlert in alert_list:
            filter = { '_id': oldAlert["_id"] }
            replacement = { '$set' : {"status": 2}}
            alert_table.find_one_and_update(filter, replacement, return_document = ReturnDocument.AFTER)

    def sendSms(self,alert_list,tokenId,link,price,rank):
        sent = []
        for alerts in alert_list:
            new_line = "\n"
            nft_collection = str(alerts["collection"])
            userPhone = self.getPhoneFromAlert(alerts)
            if int(rank) == 1000000:
                smsBody = f'Token {tokenId} from the {nft_collection} NFT collection was just listed for {price} ETH {new_line}Link: {link}'
            else:
                smsBody = f'Token {tokenId} from the {nft_collection} NFT collection was just listed for {price} ETH {new_line}Rank: {rank}{new_line}Link: {link}'
            sid = self.sms.send_message(userPhone, smsBody)
            if sid:
                sent.append({"sid": sid, "alertId" : alerts["_id"], "username": alerts["username"]})
#        print("Before sent")
#        print(sent)
        return sent

    def create_discord_alerts(self,alerts):
        discord_alerts = []
        for alert in alerts:
            discord_alerts.append({"createdAt": datetime.now(), "updatedAt": datetime.now(), "username": alert['username'], "status": 1, "message": alert["message"]})
        if len(discord_alerts) > 0:
            self.discord_alerts_table.insert_many(discord_alerts)

    def createSms(self,confirmations):
        sms = []
        for confirmation in confirmations:
            sms.append({"createdAt": datetime.now(), "updatedAt": datetime.now(), "sid": confirmation['sid'], "username": confirmation["username"], "alertId": confirmation["alertId"]})
        if len(sms) > 0:
            self.sms_table.insert_many(sms)

    def discOrSmsAlert(self, alerts):
        smsAlerts = [alert for alert in alerts if alert['delivery_method'] == 'sms']
        discordAlerts = [alert for alert in alerts if alert['delivery_method'] == 'discord']
        return smsAlerts, discordAlerts

    def getDiscordName(self,username):
        user = self.user_table.find_one({"username": username})
        return user['discord_id']

    def writeDiscordAlerts(self,alert_list,item_num,item_price,item_link,rank):
        discord_messages = []
        for alert in alert_list:
            discord_username = self.getDiscordName(alert['username'])
            new_line = "\n"
            if int(rank) == 1000000:
                message = f'{alert["collection"]} {item_num} was just listed for {item_price} ETH {new_line}Link: {item_link}'
            else:
                message = f'{alert["collection"]} {item_num} was just listed for {item_price} ETH {new_line}Rank: {rank}{new_line}Link: {item_link}'
            discord_messages.append({'message': message, 'username': discord_username})
        return discord_messages
               

