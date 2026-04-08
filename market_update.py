# market_update.py

import requests

class MarketDataFetcher:
    def __init__(self, api_url):
        self.api_url = api_url

    def fetch_data(self):
        response = requests.get(self.api_url)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception('API request failed with status: {}'.format(response.status_code))

# Example usage
if __name__ == '__main__':
    api_url = 'https://api.example.com/market'
    fetcher = MarketDataFetcher(api_url)
    data = fetcher.fetch_data()
    print(data)