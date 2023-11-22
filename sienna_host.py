# Loads a Sienna dump and presents it.

import argparse
import copy
import datetime
import jinja2
import json
import pytimeparse
import sys

from http.server import HTTPServer, BaseHTTPRequestHandler
from jinja2 import Environment, FileSystemLoader, select_autoescape
from urllib.parse import urlparse
from urllib.parse import parse_qs

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
    int_color = vehicle['intColor']
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
    other_options = []
    badges = []
    desirability = 0
    for opt in options:
      code = opt['optionCd']
      if code == 'AC':
        notable_options.append('1500W Inverter')
        badges.append('🔌')
      elif code == 'EY':
        notable_options.append('Rear Entertainment')
        badges.append('📺')
        desirability += 1
      elif code == 'DH':
        notable_options.append('Tow Hitch')
        badges.append('🔗')
        desirability += 1
      elif code == 'XL':
        notable_options.append('XLE+ Package')
        badges.append('➕')
      elif code == 'XS':
        notable_options.append('XSE+ Package')
        badges.append('➕')
      elif code == 'ST':
        notable_options.append('Spare Tire ')
        badges.append('🛞')
        desirability += 1
      elif code == 'RR':
        notable_options.append('Roof Rails')
      elif code not in (
          # 50 State Emissions
          'FE',
          # Owner's Portfolio
          'DK',
          ):
        name = opt['marketingName']
        if name:
          other_options.append(name.replace('[installed_msrp]', ''))

    if filter and desirability < args.min_desirability:
      continue

    advertised_price = price.get('advertizedPrice') or 0
    if args.max_markup is not None and advertised_price == 0:
      continue
    msrp = price.get('totalMsrp') or 0
    markup = 0 if advertised_price <= msrp else advertised_price - msrp
    if args.max_markup is not None and markup > args.max_markup:
      continue

    seen_time = None
    observe_metadata = cache.get(Cache.VIN_SEEN, vin)
    if observe_metadata.get('date_from_epoch'):
      seen_time = datetime.datetime.fromtimestamp(observe_metadata['date_from_epoch'])

    info = {
      'seen_time': seen_time,
      'title': model['marketingTitle'],
      'model': model['marketingName'],
      'vin': vin,
      'badges': ''.join(badges),
      'status': status,
      'desirability': desirability,
      'notable_options': notable_options,
      'other_options': other_options,
      'drivetrain': drivetrain['code'],
      'dealer_name': vehicle['dealerMarketingName'],
      'dealer_website': vehicle['dealerWebsite'],
      'color': ext_color['marketingName'],
      'intColor': int_color['marketingName'],
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


def serve(port, cache, get_infos):
  env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(),
  )

  class Server(BaseHTTPRequestHandler):
    def do_GET(self):
      print('Handling GET path:', self.path)

      self.send_response(200)
      self.send_header("Content-type", "text/html")
      self.end_headers()

      template = env.get_template('index.html')

      # Update each info from cache.
      filtered_infos = []
      for info in get_infos():
        info = copy.deepcopy(info)
        state_entry = cache.get(Cache.REMOVED, info['vin'])
        if state_entry:
          if state_entry.get('state') is None:
            # (Legacy) state is not populated, "removed" implied.
            continue
          info['state'] = state_entry.get('state')
          if info['state'] == 'REMOVED':
            # (Current) state is explicit
            continue
        filtered_infos.append(info)
          
      self._write(template.render(vehicles=filtered_infos))

    def do_POST(self):
      print('Handling POST path:', self.path)
      data_string = self.rfile.read(int(self.headers.get('Content-Length', 0)))
      parts = data_string.decode('utf-8').split('=')
      print(parts)
      if len(parts) == 2:
        if parts[0] == 'removeVin':
          self._remove_vin(parts[1])
        elif parts[0] == 'markVin':
          self._mark_vin(parts[1])

      redirect_url = '/'
      parsed_url = urlparse(self.path)
      anchor = parse_qs(parsed_url.query).get('anchor')
      if anchor:
        redirect_url += '#' + anchor[0]

      # Redirect to main page.
      self.send_response(301)
      self.send_header('Location', redirect_url)
      self.end_headers()


    def _write(self, data):
      self.wfile.write(bytes(data, 'utf-8'))

    def _remove_vin(self, vin):
      print('Removing VIN:', vin)
      now = datetime.datetime.now()
      cache.put(Cache.REMOVED, vin,
                {'state': 'REMOVED', 'time': now.timestamp()})

    def _mark_vin(self, vin):
      print('Marking VIN:', vin)
      now = datetime.datetime.now()
      cache.put(Cache.REMOVED, vin,
                {'state': 'MARKED', 'time': now.timestamp()})



  HOSTNAME = '0.0.0.0'
  print("Server started http://%s:%s" % (HOSTNAME, port))
  with HTTPServer((HOSTNAME, port), Server) as server:
    server.serve_forever()
  print("Server closed")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('input')
  parser.add_argument('--cache', required=True)
  parser.add_argument('--port',  default=8080, type=int)
  parser.add_argument('--filter', action='store_true')
  parser.add_argument('--min_desirability', default=1, type=int)
  parser.add_argument('--sort', default='distance')
  parser.add_argument('--since',  default=None, 
                      action=TimeDeltaAction)
  parser.add_argument('--max_markup',  default=None, type=int)
  args = parser.parse_args()

  cache = Cache(args.cache)

  def get_infos():
    with open(args.input, 'r') as fd:
      vehicles = json.load(fd)

    infos = load_infos(cache, args, vehicles)
    print('Loaded %d filtered vehicles from %d original vehicle(s)...' % (
      len(infos), len(vehicles),))

    if args.sort == 'distance':
      infos.sort(key=lambda x: x['distance'])
    elif args.sort == 'newest':
      infos.sort(key=lambda x: x['seen_time'], reverse=True)

    return infos
  
  if args.port != 0:
    serve(args.port, cache, get_infos)
  else:
    for info in get_infos():
      print('  - %r' % (info,))



if __name__ == '__main__':
  sys.exit(main())
