import re
import boto3
import string
import os
import random
import json

dynamodb = boto3.client('dynamodb')


def lambda_handler(event, context):

    print(event)
    method = event['httpMethod']

    # Get the domain be referenced (either example.com/redirect
    # or ...amazonaws.com) stage will be omitted if the API is behind a
    # domain (rather than the api gateway dns)
    domain = get_domain(event)

    if method == 'GET':

        # Called if the user hits the /redirect resource

        if event['resource'] == '/redirect':
            return api_website(event, domain)

        # Called if the user is trying to hit a shortened url
        # the pathParameters will contain the http://.../redirect/token_id
        # therefore the pathParameters will not be empty
        elif event['pathParameters'] is not None:
            return retrieve_url(event, domain)

    if method == 'POST':
        return create_new_url(event, domain)

    return {
                        "statusCode": 200,
                        "headers": {
                            "Content-Type": 'text/html',
                            "Access-Control-Allow-Origin": "*"
                        },
                        "body": "HTTP method not supported."
    }


def create_new_url(event, domain):

    post_body = event['body']
    url = json.loads(post_body)['destination_url']

    # If the user provided a custom token, use that token. Otherwise,
    # generate a new token
    token = json.loads(post_body)['custom_token'] if 'custom_token' in \
                json.loads(post_body) else generate_token()

    return_payload = {
                        "statusCode": 200,
                        "headers": {
                            "Content-Type": 'text/html',
                            "Access-Control-Allow-Origin": "*"
                        }
                     }

    # Validates URL from post_body
    if not validate_url(url):
        return_payload['body'] = "The provided URL is invalid.\n"
        return return_payload

    # Put the token and url into DynamoDB
    response = dynamodb.put_item(TableName=os.environ['dynamodb_table'],
                                Item={'id': {'S': "{}".format(token)},
                                       'destination_url':{'S':url}
                                })
    print(response)
    # if the consumer requested a JSON payload in return,
    # return json, otherwise just return a string
    if 'application/json' in event['headers']['Accept']:
        return_payload['headers']['Content-Type'] = 'application/json'
        return_payload['body'] = json.dumps({
            'shortened_url': '{domain}/{token}'.format(domain=domain,
                                                       token=token)
        })
    else:
        return_payload['body'] = \
            "Shortened URL for {url} created. <br>".format(url=url) + \
            "The shortened url is <a href=\"{domain}/{token}\">{domain}/{token}</a><br>".format(domain=domain,
                                                             token=token)
    return return_payload


def retrieve_url(event, domain):

    return_payload = {
                        "statusCode": 301,
                        "headers": {
                            "Content-Type": 'text/html',
                            "Access-Control-Allow-Origin": "*"
                        }
                     }

    token = event['pathParameters']['proxy']

    # Based on the token, retrieve url from dynamodb table
    response = dynamodb.get_item(TableName=os.environ['dynamodb_table'],
                                 Key={'id': {'S': token}})

    # if the token key doesn't exist in the dynamodb table, return error body
    if 'Item' not in response:
        return_payload['statusCode'] = 200
        return_payload['body'] = "Token {} Invalid. URL Not Found\n".format(token)
        return return_payload

    # if the token was found, retrieve the URL from DynamoDB and add it to the
    # 'Location' header for the redirect
    return_payload['headers']['Location'] = response['Item']['destination_url']['S']
    return_payload['body'] = ""
    return return_payload


def generate_token():
    # Generate a random one time token
    allowed_chars = string.digits + string.ascii_letters
    return ''.join(random.SystemRandom().choice(allowed_chars)for _ in range(6))


def validate_url(url):
    # Validate the given URL
    regex = re.compile( r'^(?:http|ftp)s?://'  # http:// or https://
                        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
                        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                        r'(?::\d+)?'  # optional port
                        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    if not re.findall(regex, url):
        return False
    return True


def get_domain(event):

    # Supports test invocations from API Gateway
    if event['headers'] is None:
        return "https://testinvocation/redirect"

    # Extracts the domain from event object based on for both api gateway URLs
    # or custom domains
    if 'amazonaws.com' in event['headers']['Host']:
        return "https://{domain}/{stage}/redirect".format(domain=event['headers']['Host'],
                                                          stage=event['requestContext']['stage'])
    else:
        return "https://{domain}/redirect".format(domain=event['headers']['Host'])


def api_website(event, domain):
    # returns a website front end for the redirect tool
    body = """
    <html>
    <body bgcolor=\"#E6E6FA\">
    <head>
    <!-- Latest compiled and minified CSS -->
    <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css" integrity="sha384-BVYiiSIFeK1dGmJRAkycuHAHRg32OmUcww7on3RYdg4Va+PmSTsz/K68vbdEjh4u" crossorigin="anonymous">
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.1.1/jquery.min.js"></script>
    <style>
    .form {
        padding-left: 1cm;
    }

    .div{
      padding-left: 1cm;
    }
    </style>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.1.1/jquery.min.js"></script>
    <script>

    $(document).ready(function(){
        $("button").click(function(){
          var destinationUrl = document.getElementById("destinationUrl").value;
          var dict = {};
          dict["destination_url"] = destinationUrl;
          if (document.getElementById("customToken").value != "") {
              dict["custom_token"] = document.getElementById("customToken").value;
          }

          $.ajax({
            type: 'POST',
            headers: {
                'Content-Type':'application/json',
                'Accept':'text/html'
            },
            url:'$domain',
            crossDomain: true,
            data: JSON.stringify(dict),
            dataType: 'text',
            success: function(responseData) {
                document.getElementById("id").innerHTML = responseData;
            },
            error: function (responseData) {
                alert('POST failed.'+ JSON.stringify(responseData));
            }
          });
        });
    });
    </script>
    </head>
    <title>Serverless URL Redirect</title>
    <h1 class="div">Serverless URL Redirect</h1>
    <body>

      <form class="form" action="" method="post">
            <textarea rows="1" cols="50" name="text" id="destinationUrl" placeholder="Enter URL (http://www.example.com)"></textarea>
      </form>
      <form class="form" action="" method="post">
            <textarea rows="1" cols="50" name="text" id="customToken" placeholder="Use Custom Token (domain.com/redirect/custom_token)"></textarea>
      </form>


    <div class="div"><button class="btn btn-primary">Shorten URL</button></div>
    <div class="div" id='id'></div>
    </body>
    </html>
    """

    return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": 'text/html',
                    "Access-Control-Allow-Origin": "*"
                },
                "body": string.Template(body).safe_substitute({"domain": domain})
    }
