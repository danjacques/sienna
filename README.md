# Sienna Finder Thing

This repository hosts two scripts:

-   `sienna_fetch.py`, intended to be run as a `cron` which loads data from Toyota.
-   `sienna_host.py`, a persistent webserver which hosts the data generated by `sienna_fetch.py`.

## Installation

Install a VirtualEnv:

```
git clone <repo>
cd <repo>
pip install virtualenv
virtualenv venv
source venv/bin/activate
pip install -r environment.txt
```

## Usage

### `sienna_fetch.py`

Run the fetch script, specifying values for the following flags:

-   `--output`: Location of the output JSON file, which will be loaded by `sienna_host.py`.
-   `--cache`: Location of the cache directory (required!)
-   `--zip`: ZIP code to center the search radius on. Use yours.
-   `--aws_waf_token`: The WAF token value.

Optional overrides:
-   `--page_size`: The page size. Too large and Toyota rejects. I've done OK with 500-1000, default is 250 I think?
-   `--distance_miles`: Search radius. Default is crap, I think 500-1000 is reasonable depending on how far you're willing to drive.

#### AWS WAF Token

The AWS WAF token is new. I originally ran this as a `cron` job, but apparently Toyota has started protecting its access using AWS WAF, which uses short-lived Captcha tokens. We could embed a Captcha in the `sienna_fetch.py` webpage and use that to supply the token and trigger a fetch; however, this is more work than I want to do. Instead, you have to get a WAF token every time you run "fetch" and supply it to the command-line. You can do this by:

1.   Open Chrome, open the inspector.
2.   Load the Toyota search page: https://www.toyota.com/search-inventory/model/sienna/
3.   Look for a request to the `/graphql` endpoint.
4.   Find the `X-Aws-Waf-Token` header and copy its value.
5.   Paste this value directly into the `--aws_waf_token` page.

### `sienna_host.py`

You can run this by calling:

```sh
python sienna_host.py <path_to_output> --filter --cache=<path_to_cache> --sort=newest
```

It hosts a webpage that's somehow better than Toyota's own search. Refreshing this webpage will refresh the backing data so you don't need to restart the server every time you run "fetch". You can delete entries from the webpage and it'll show you things like MSRP deltas and useful information about each vehicle. It'll also promote dealer metadata to the front so you don't have to click on every link to see who to contact.

Play around with flags if you want other things. You may have to chance the source code to make it do exactly what you want.