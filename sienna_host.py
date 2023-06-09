# Loads a Sienna dump and presents it.

import argparse
import datetime
import jinja2
import json
import pytimeparse
import sys

from http.server import HTTPServer, BaseHTTPRequestHandler
from jinja2 import Environment, FileSystemLoader, select_autoescape

from util.cache import Cache

class TimeDeltaAction(argparse.Action):
    """Resolve paths during argument parsing"""

    def __call__(self, parser, namespace, values, option_string=None):
      setattr(namespace, self.dest,
              datetime.timedelta(seconds=pytimeparse.timeparse.timeparse(values)))



def get_dealer_phone(dealer):
  dealer_locators = dealer['showDealerLocatorDataArea']['dealerLocator']
  for locator in dealer_locators:
    for detail in locator['dealerLocatorDetail']:
      for contact in detail['dealerParty']['specifiedOrganization']['primaryContact']:
        for entry in contact.get('telephoneCommunication', []):
          if entry.get('channelCode', {}).get('value') == 'Phone':
            value = entry['completeNumber']['value']
            if len(value) == 10:
              return '(%s)-%s-%s' % (value[:3], value[3:6], value[6:])
            else:
              return value
  return None
    

def get_dealer_address(dealer):
  dealer_locators = dealer['showDealerLocatorDataArea']['dealerLocator']
  for locator in dealer_locators:
    for detail in locator['dealerLocatorDetail']:
      for contact in detail['dealerParty']['specifiedOrganization']['primaryContact']:
        postal = contact.get('postalAddress')
        if not postal:
          continue

        addr_parts = [
          postal['lineOne']['value'],
          postal['cityName']['value'],
          postal['stateOrProvinceCountrySubDivisionID']['value'],
          postal['postcode']['value'],
        ]
        return ' '.join(addr_parts)
  return None


def load_infos(cache, args, vehicles):
  cutoff = None
  if args.since:
    now = datetime.datetime.now()
    cutoff = now - args.since

  infos = []
  for vehicle in vehicles:
    price = vehicle['price']
    ext_color = vehicle['extColor']
    drivetrain = vehicle['drivetrain']
    options = vehicle['options']
    model = vehicle['model']
    eta = vehicle['eta']
    vin = vehicle['vin']

    if cutoff:
      seen = cache.get(Cache.VIN_SEEN, vin)
      if seen:
        seen_time = datetime.datetime.fromtimestamp(seen['date_from_epoch'])
        if seen_time < cutoff:
          continue

    # Filter on model
    if args.filter and model['marketingName'] not in (
        'Sienna XLE',
        'Sienna XSE',
        ):
      continue

    status = []
    available = True
    if vehicle.get('isPreSold', False):
      status.append('PRE_SOLD')
      available = False
    if vehicle.get('holdStatus'):
      status.append(vehicle['holdStatus'])
      available = False
    status = None if len(status) == 0 else '; '.join(status)
    if filter and not available:
      continue

    notable_options = []
    has_desired_options = False
    for opt in options:
      code = opt['optionCd']
      if code == 'AC':
        notable_options.append('1500W-INVERTER')
      elif code == 'EY':
        notable_options.append('REAR-ENTERTAINMENT')
        has_desired_options = True
      elif code == 'DH':
        notable_options.append('TOW-HITCH')
        has_desired_options = True
      elif code == 'XL':
        notable_options.append('XLE+')
      elif code == 'XS':
        notable_options.append('XSE+')
      elif code == 'ST':
        notable_options.append('SPARE')
    if filter and not has_desired_options:
      continue

    advertised_price = price.get('advertizedPrice') or 0
    if args.max_markup is not None and advertised_price == 0:
      continue
    msrp = price.get('totalMsrp') or 0
    markup = 0 if advertised_price <= msrp else advertised_price - msrp
    if args.max_markup is not None and markup > args.max_markup:
      continue


    info = {
      'title': model['marketingTitle'],
      'model': model['marketingName'],
      'vin': vin,
      'status': status,
      'options': notable_options,
      'drivetrain': drivetrain['code'],
      'dealer_name': vehicle['dealerMarketingName'],
      'dealer_website': vehicle['dealerWebsite'],
      'color': ext_color['marketingName'],
      'distance': vehicle['distance'],
      'msrp': msrp,
      'advertised_price': advertised_price,
      'price_markup': markup,
    }



    # Resolve dealer metadata.
    dealer = cache.get(Cache.DEALER, vehicle.get('dealerCd'))
    info['dealer_phone'] = get_dealer_phone(dealer)
    info['dealer_address'] = get_dealer_address(dealer)

    infos.append(info)
  return infos


def serve(port, infos):
  env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(),
  )

  class Server(BaseHTTPRequestHandler):
    def do_GET(self):
      self.send_response(200)
      self.send_header("Content-type", "text/html")
      self.end_headers()

      template = env.get_template('index.html')
      self._write(template.render(vehicles=infos))

    def _write(self, data):
      self.wfile.write(bytes(data, 'utf-8'))



  HOSTNAME = 'localhost'
  server = HTTPServer((HOSTNAME, port), Server)
  print("Server started http://%s:%s" % (HOSTNAME, port))
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    pass

  server.server_close()
  print("Server closed")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('input')
  parser.add_argument('--cache', required=True)
  parser.add_argument('--port',  default=8080, type=int)
  parser.add_argument('--filter', action='store_true')
  parser.add_argument('--since',  default=None, 
                      action=TimeDeltaAction)
  parser.add_argument('--max_markup',  default=None, type=int)
  args = parser.parse_args()

  cache = Cache(args.cache)
  with open(args.input, 'r') as fd:
    vehicles = json.load(fd)

  print('Loaded %d vehicle(s)...' % (len(vehicles),))
  infos = load_infos(cache, args, vehicles)
  
  if args.port != 0:
    serve(args.port, infos)
  else:
    infos.sort(key=lambda x: x['distance'])
    for info in infos:
      print('  - %r' % (info,))



if __name__ == '__main__':
  sys.exit(main())