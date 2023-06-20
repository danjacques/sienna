# Program to fetch Toyota Sienna listings.

import argparse
import datetime
import os
import requests
import json

from util.cache import Cache

HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
  'Content-Type': 'application/json',
}


class Query:
  zip = 22124
  page_size = 250
  distance_miles = 200
  pass


def load_page(query, page_number):
  endpoint = 'https://api.search-inventory.toyota.com/graphql'
  graphql_query = """
query {
    locateVehiclesByZip(
        zipCode: \"%(zip)s\",
        brand: \"TOYOTA\",
        pageNo: %(page_number)d,
        pageSize: %(page_size)d,
        seriesCodes: \"sienna\",
        distance: %(distance_miles)d,
        leadid: \"800c67b5-b4d0-4d47-acca-a26b4cfb6f1c\"
      ) {
      pagination {
        pageNo
        pageSize
        totalPages
        totalRecords
      }
      vehicleSummary {
        vin
        stockNum
        brand
        marketingSeries
        year
        isTempVin
        dealerCd
        dealerCategory
        distributorCd
        holdStatus
        weightRating
        isPreSold
        dealerMarketingName
        dealerWebsite
        isSmartPath
        distance
        isUnlockPriceDealer
        transmission {
          transmissionType
        }
        price {
          advertizedPrice
          nonSpAdvertizedPrice
          totalMsrp
          sellingPrice
          dph
          dioTotalMsrp
          dioTotalDealerSellingPrice
          dealerCashApplied
          baseMsrp
        }
        options {
          optionCd
          marketingName
          marketingLongName
          optionType
          packageInd
        }
        mpg {
          city
          highway
          combined
        }
        model {
          modelCd
          marketingName
          marketingTitle
        }
        media {
          type
          href
          imageTag
          source
        }
        intColor {
          colorCd
          colorSwatch
          marketingName
          nvsName
          colorFamilies
        }
        extColor {
          colorCd
          colorSwatch
          marketingName
          colorHexCd
          nvsName
          colorFamilies
        }
        eta {
          currFromDate
          currToDate
        }
        engine {
          engineCd
          name
        }
        drivetrain {
          code
          title
          bulletlist
        }
        family
        cab {
          code
          title
          bulletlist
        }
        bed {
          code
          title
          bulletlist
        }
      }
    }
  }
  """ % {
    'zip': query.zip,
    'page_number': page_number,
    'page_size': query.page_size,
    'distance_miles': query.distance_miles,
  }

  data = {
    'query': graphql_query,
  }
  r = requests.post(endpoint, headers=HEADERS, data=json.dumps(data))
  if r.status_code != 200:
    raise Exception('Failed to get data (%d): %s' % (r.status_code, r.text))
  return r.json()


def load_smartpath_dealer(cache, dealer_code):
  cached = cache.get(Cache.DEALER, dealer_code)
  if cached:
    return cached

  endpoint = 'https://smartpath.toyota.com/service/tcom/dealerDetail/dealerCode/%s' % (dealer_code,)
  r = requests.get(endpoint, headers=HEADERS)
  result = r.json()
  return cache.put(Cache.DEALER, dealer_code, result)


def load_dealer(cache, dealer_code):
  cached = cache.get(Cache.DEALER, dealer_code)
  if cached:
    return cached

  endpoint = 'https://api.dg.toyota.com/api/v2/dealers/%s?brand=toyota' % (dealer_code,)
  r = requests.get(endpoint, headers=HEADERS)
  result = r.json()
  print('Loaded dealer %s!' % (dealer_code,))
  return cache.put(Cache.DEALER, dealer_code, result)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--zip', default=Query.zip)
  parser.add_argument('--page_size', default=Query.page_size,
                      type=int)
  parser.add_argument('--distance_miles',
                      default=Query.distance_miles, type=int)
  parser.add_argument('--output', required=True)
  parser.add_argument('--cache', required=True)
  args = parser.parse_args()

  query = Query()
  query.zip = args.zip
  query.page_size = args.page_size
  query.distance_miles = args.distance_miles
  
  output = []
  for i in range(1, 1000):
    print('Loading page %d...' % (i,))
    result = load_page(query, i)

    response = result.get('data', {}).get('locateVehiclesByZip', {})
    if response is None:
      break

    output.extend(response.get('vehicleSummary', []))
    print('Have responses: %d' % (len(output),))

    pagination = response.get('pagination', {})
    if i >= pagination.get('totalPages', 0):
      break

  cache = Cache(args.cache)
  seen_dealers = set()
  now = datetime.datetime.now()
  for out in output:
    # Load dealer information.
    dealer_code = out['dealerCd']
    if dealer_code not in seen_dealers:
      seen_dealers.add(dealer_code)
      load_dealer(cache, dealer_code)

    # Load VIN-seen information.
    vin = out['vin']
    if not cache.exists(Cache.VIN_SEEN, vin):
      print('New vehicle [%s]: %s' % (vin, now))
      cache.put(Cache.VIN_SEEN, vin, {'date_from_epoch': now.timestamp()})

  if os.path.exists(args.output):
    os.rename(args.output, args.output + '_%d' % (now.timestamp(),))
  with open(args.output, 'w') as fd:
    json.dump(output, fd, indent='  ')


if __name__ == '__main__':
  main()