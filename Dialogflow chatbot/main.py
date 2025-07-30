
import os
from fastapi import FastAPI
from fastapi import Request
from google.cloud import dialogflow_v2 as dialogflow

import uuid
from fastapi.responses import JSONResponse
import db_helper
import generic_helper
app = FastAPI()

inprogress_orders = {}


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/Users/sourav/pythonProject/fastapi/credentials/dialogflow_key.json"


@app.get("/chat")
def chat_with_bot(text: str):

    project_id = "dialogflow-464315"

    session_id = str(uuid.uuid4())

    session_client = dialogflow.SessionsClient()
    session = session_client.session_path(project_id, session_id)

    text_input = dialogflow.TextInput(text=text, language_code="en-US")
    query_input = dialogflow.QueryInput(text=text_input)

    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )

    return {"response": response.query_result.fulfillment_text}

@app.post("/")
async def handle_request(request: Request):
    # Retrieve the JSON data from the request
    payload = await request.json()

    # Extract the necessary information from the payload
    # based on the structure of the WebhookRequest from Dialogflow
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    output_contexts = payload['queryResult']['outputContexts']

    session_id = generic_helper.extract_session_id(output_contexts[0]['name'])
    intent_handler_dict={
        'order.add - context: ongoing-order': add_to_order,
        'order.remove - context: ongoing-order': remove_from_order,
        'order.complete - context: ongoing-order': complete_order,
        'track.order - context: ongoing-tracking': track_order

    }
    return intent_handler_dict[intent](parameters, session_id)

def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! can you place a new order"
        })
    current_order=inprogress_orders[session_id]
    food_items=parameters["food-item"]
    removed_items=[]
    no_such_items=[]
    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]
    if len(removed_items)>0:
        fulfillment_text=f'Removed {",".join(removed_items)} from your orders'
    if len(no_such_items)>0:
        fulfillment_text = f'Your current order does not have {",".join(no_such_items)}'
    if len(current_order.keys()) == 0:
        fulfillment_text +=" Your order is Empty!"
    else:
        order_str= generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text +=f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })
def add_to_order(parameters: dict, session_id:str):
    food_items=parameters["food-item"]
    quantities=parameters["number"]
    if len(food_items)!=len(quantities):
         fulfillment_text="Sorry I didn't understand. can you please specidy food items and quantity"
    else:
        new_food_dict = dict(zip(food_items, quantities))
        if session_id in inprogress_orders:
            current_food_dict=inprogress_orders[session_id]
            current_food_dict.update(new_food_dict)
            inprogress_orders[session_id]=current_food_dict
        else:
            inprogress_orders[session_id]=new_food_dict

        order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])

        fulfillment_text = f"so far you have: {order_str} . Do you need anything else?"
    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def complete_order(parameters: dict, session_id:str):
    if session_id not in inprogress_orders:
        fulfillment_text="I'm having a trouble finding your orders. Sorry! can you place anew order"
    else:
        order = inprogress_orders[session_id];
        order_id = save_to_db(order)
        if order_id==-1:
            fulfillment_text="Sorry, I couldn't process your order due to backend error."\
                             "please place a new order again"
        else:
            order_total=db_helper.get_total_order_price(order_id)
            fulfillment_text=f"Awesome. we have placed your order. "\
                             f"Here is your order id #{order_id}. "\
                             f"Your order total is {order_total} which you can pay at the time of delivery!"

        del inprogress_orders[session_id]

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

def save_to_db(order: dict):
    next_order_id=db_helper.get_next_order_id()
    for food_item, quantity in order.items():
        rcode= db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )
        if rcode == -1:
            return -1

    db_helper.insert_order_tracking(next_order_id, "in progress")


    return next_order_id
def track_order(parameters: dict,session_id: str ):
    order_id=parameters['order_id']
    order_status=db_helper.get_order_status(order_id)
    if order_status:
        fulfillment_text=f"The order status for order is: {order_id} is: {order_status}"
    else:
        fulfillment_text = f"no order status for order is: {order_id}"
    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

