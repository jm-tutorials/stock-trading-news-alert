import os
import json
from datetime import datetime, timedelta
from dateutil import tz
import re

import requests
import pandas as pd
from twilio.rest import Client
# from twilio.http.http_client import TwilioHttpClient


# stock variables
STOCK_SYMBOL = "TSLA"
STOCK_FUNCTION = "TIME_SERIES_DAILY_ADJUSTED"
STOCK_INTERVAL = "60min"
STOCK_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY")

# news variables
COMPANY_NAME = "Tesla Inc"
NEWS_API_KEY = os.environ.get("NEWSAPI_API_KEY")

class StockNews:

    def get_data(self, url):
        response = requests.get(url)
        response.raise_for_status()
        print(response.status_code)
        return response.json()

    def convert_to_timestamp(self, timestamp_string, dformat):
        timestamp = datetime.strptime(timestamp_string, dformat)
        return self.convert_timezone(timestamp, from_timezone=self.timezone)

    def convert_timezone(self, timestamp, from_timezone=None, to_timezone=None):
        if from_timezone is None:
            from_zone = tz.tzlocal()
            timestamp = timestamp.replace(tzinfo=from_zone)
            if to_timezone is None:
                return timestamp
            else:
                to_zone = tz.gettz(to_timezone)
        else:
            from_zone = tz.gettz(from_timezone)
            to_zone = tz.gettz(to_timezone)
            timestamp = timestamp.replace(tzinfo=from_zone)
        return timestamp.astimezone(to_zone)

    # STEP 1: Use https://www.alphavantage.co
    # When STOCK price increase/decreases by 5% between yesterday and the day before yesterday then print("Get News").
    def get_stock_data(self):
        url = f"https://www.alphavantage.co/query?function={STOCK_FUNCTION}&symbol={STOCK_SYMBOL}&interval={STOCK_INTERVAL}&apikey={STOCK_API_KEY}"
        stock_data = self.get_data(url)

        self.meta_data = stock_data['Meta Data']
        self.timezone = self.meta_data['5. Time Zone']
        self.company_symbol = self.meta_data['2. Symbol']

        # get past 3 days
        today = self.convert_timezone(datetime.now(), self.timezone).date()
        self.yesterday = today - timedelta(days=1)
        self.day_before_yesterday = self.yesterday - timedelta(days=1)

        with open('data/daily_stock_data_sample.json', 'w') as f:
            json.dump(stock_data, f)

        stock_data_formatted = []
        for day, values in stock_data['Time Series (Daily)'].items():
            stock_datum_formatted = {'date_day': self.convert_to_timestamp(day, '%Y-%m-%d').date()}
            stock_datum_formatted.update({k.split('. ')[1].strip().replace(' ', '_'): float(v) for k, v in values.items()})
            stock_data_formatted.append(stock_datum_formatted)

        self.stock_df = pd.DataFrame(stock_data_formatted).sort_values('date_day')
        self.stock_df['prior_day_close'] = self.stock_df.adjusted_close.shift(1)
        self.stock_df['dod_close_delta'] = (self.stock_df.adjusted_close - self.stock_df.prior_day_close)/self.stock_df.prior_day_close

        print(self.stock_df.tail())
        print(self.yesterday)
        self.yesterday_close_details = self.stock_df.loc[self.stock_df.date_day == self.yesterday,
                                                         ['adjusted_close', 'prior_day_close', 'dod_close_delta']]

    # STEP 2: Use https://newsapi.org
    # Instead of printing ("Get News"), actually get the first 3 news pieces for the COMPANY_NAME.
    def get_news(self, company_name, from_date, to_date, sort_by='publishedAt'):
        news_url = f"https://newsapi.org/v2/everything?q={company_name}&from={from_date}&sortBy={sort_by}&apiKey={NEWS_API_KEY}"
        self.news_data = self.get_data(news_url)
        self.news_results = self.news_data['articles']
        self.format_message()

    def format_message(self):
        try:
            if self.yesterday_close_details.dod_close_delta.iloc[0] > 0:
                arrow = f'🔺{self.yesterday_close_details.dod_close_delta[0]:.0f}'
            elif 0.049 > self.yesterday_close_details.dod_close_delta.iloc[0] > -0.049:
                arrow = f' {self.yesterday_close_details.dod_close_delta[0]:.0f}'
            else:
                arrow = f'🔻{self.yesterday_close_details.dod_close_delta[0]:.0f}'
        except Exception as e:
            print(f'🔻{self.yesterday_close_details.dod_close_delta[0]}')
            print(e)

        top_results = [f"Headline: {article['title']}\nBrief: {article['description']}\nRead More: {article['url']}" for article in self.news_results[0:3]]
        top_results_s = '\n'.join(top_results)

        self.message = f"""
        {self.company_symbol}: {arrow}
        {top_results_s}
        """

    # STEP 3: Use https://www.twilio.com
    # Send a seperate message with the percentage change and each article's title and description to your phone number.
    def send_message(self):
        # uncomment below two lines and line 10 if scheduling via pythoneverywhere
        # proxy_client = TwilioHttpClient()
        # proxy_client.session.proxies = {'https': os.environ('https_proxy')}

        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_ACCOUNT_AUTH_TOKEN')
        client = Client(account_sid, auth_token)

        message = client.messages \
            .create(body=self.message,
                    from_='+17753414072',
                    to='+13038159390'
                    )
        print(message.status)

    def controller(self):
        self.get_stock_data()
        if abs(self.yesterday_close_details.dod_close_delta[0]) >= .5:
            from_date = self.yesterday - timedelta(days=3)
            self.get_news(COMPANY_NAME, from_date=from_date, to_date=self.yesterday)
            print(self.message)
            self.send_message()


if __name__ == '__main__':
   stonks = StockNews()
   stonks.controller()

