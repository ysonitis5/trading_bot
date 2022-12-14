import time
import logging
from datetime import timedelta, datetime
import ccxt
import pandas as pd
from ccxt import kucoinfutures

import dontshare_config as ds

'''
capitulation bot based off volume or some sort of bot off volume
'''

logging.basicConfig(filename='log.log', encoding='utf-8', level=logging.DEBUG)


kucoin: kucoinfutures = ccxt.kucoinfutures({
    'enableRateLimit': True,
    'apiKey': ds.kuKey,
    'secret': ds.kuSec,
    'password': ds.password
})


#
'''
organized list of symbol and ID
marketdf = pd.DataFrame(kucoin.load_markets()).transpose()
print(marketdf.to_string())
'''

symbol = 'LINK/USDT:USDT'
pos_size = 1200
params = {'timeinforce': 'postonly', 'leverage': 40}
target = 15
risktolerance = -5


#DAILY SMA 20

# ask_bid()[0] = ask, [1] = bid
def ask_bid():

    ob = kucoin.fetch_order_book(symbol)
   # print(ob)

    bid = ob['bids'][0][0]
    ask = ob['asks'][0][0]

    return ask, bid # ask_bid()[0] = ask, [1] = bid

def daily_sma():

    print('___________________________')

    timeframe = '4h'
    num_bars = 100

    bars = kucoin.fetch_ohlcv(symbol, timeframe=timeframe, limit=num_bars)
    df_d = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_d['timestamp'] = pd.to_datetime(df_d['timestamp'], unit='ms')

    # DAILY SMA - 20 DAY
    df_d['sma20_d'] = df_d.close.rolling(20).mean()

    # if bid < the 20 day sma then = BEARISH, if bid > 20 day sma = BULLISH
    bid = ask_bid()[1]

    #if sma > bid = SELL. if sma < BUY
    df_d.loc[df_d['sma20_d']>bid, 'sig'] = 'SELL'
    df_d.loc[df_d['sma20_d']<bid, 'sig'] = 'BUY'

    #print(df_d)

    return df_d

#15MIN SMA 20

def f15_sma():

    print('firing indicators...')
    ct = datetime.now()
    print("current time:-", ct)

    timeframe = '15m'
    num_bars = 100

    bars = kucoin.fetch_ohlcv(symbol, timeframe=timeframe, limit=num_bars)
    df_f = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df_f['timestamp'] = pd.to_datetime(df_f['timestamp'], unit='ms')

    # 15M SMA - 20 DAY
    df_f['sma20_15'] = df_f.close.rolling(20).mean()

    # BUY PRICE 1+2 AND SELL PRICE +2 (THEN LATER FIGURE OUT WHICH I CHOSE)
    # buy or sell to open around the 15m sma - .1% under and .3% over
    df_f['bp_1'] = df_f['sma20_15'] * 1.001 #15m sma .1% under and .3% over
    df_f['bp_2'] = df_f['sma20_15'] * .997
    df_f['sp_1'] = df_f['sma20_15'] * .999
    df_f['sp_2'] = df_f['sma20_15'] * 1.003

    #print(df_f)

    return df_f

    # SET BUY OR SELL TO OPEN PRICE IN DF


df_d = daily_sma()
df_f = f15_sma()
ask = ask_bid()[0]
bid = ask_bid()[1]
# determine the trend

def open_positions():
    params = {'type':'swap', 'code':'USD'}
    ku_bal = kucoin.fetch_positions(symbols=[symbol], params=params)
    open_positions = ku_bal[0]['collateral']
    openpos_side = ku_bal[0]['side']
    openpos_size = ku_bal[0]['contracts']
    tradesym = ku_bal[0]['symbol']

    if openpos_side == ('long'):
        openpos_bool = True
        long = True
    elif openpos_side == ('short'):
        openpos_bool = True
        long = False
    else:
        openpos_bool = False
        long = None

    return open_positions, openpos_bool, openpos_size, long, tradesym

# strategy - determine the trend with 20 day sma / based of trend
# ENTRY
# EXIT

def kill_switch():

    #limit close us
    print('killswitch engage >=D')
    logging.info('position was closed')
    openposi = open_positions()[1]
    long = open_positions()[3]
    kill_size = open_positions()[2]
    tradesym = open_positions()[4]

    print(f'openposi {openposi}, long {long}, size {kill_size}')

    while openposi == True:

        print('starting kill switch loop til limit fil...')
        temp_df = pd.DataFrame()
        print('just made a temp df')

        kucoin.cancel_all_orders(symbol)
        openposi = open_positions()[1]
        long = open_positions()[3]
        long = open_positions()[3]
        kill_size = open_positions()[2]
        kill_size = int(kill_size)

        ask = ask_bid()[0]
        bid = ask_bid()[1]

        if long == False:
            kucoin.create_limit_buy_order(symbol=tradesym, amount=kill_size, price=bid, params=params)
            print(f'just made a BUY to CLOSE order of {kill_size} {tradesym} at ${bid}')
            print('sleeping for 30 seconds to see if it fills..')
            time.sleep(30)

        elif long == True:
            kucoin.create_limit_sell_order(symbol=tradesym, amount=kill_size, price=ask, params=params)
            print(f'just made a SELL to CLOSE order of {kill_size} {tradesym} at ${ask}')
            print('sleeping for 30 seconds to see if it fills..')
            time.sleep(30)
        else:
            print('++++++++NOT EXPECTED KILLSWITCH FUNCTION++++++')

        openposi = open_positions()[1]



# pnl_close() [0] and in_pos [1] size [2] long [3]
def pnl_close():

    print('checking to see if its time to exit...')
    try:
        params = {'type':'swap', 'code':'USD'}
        pos_dict = kucoin.fetch_positions(symbols=[symbol], params=params)
        #print(pos_dict)
        pos_dict = pos_dict[0]
        side = pos_dict['side']
        size = pos_dict['contracts']
        entry_price = float(pos_dict['entryPrice'])
        leverage = float(pos_dict['leverage'])

        current_price = ask_bid()[1]
        print(f'side: {side} | entry_price: {entry_price} | lever: {leverage}x')

        #short or long

        if side == 'long':
            diff = current_price - entry_price
            long = True
            sellprice = (((entry_price/100) * (target/leverage)) + entry_price)
        else:
            diff = entry_price - current_price
            long = False
            sellprice = (entry_price - ((entry_price/100) * (target/leverage)))

        try:
            perc = round(((diff/entry_price) * leverage), 10)
        except:
            perc = 0

        perc = 100*perc
        print(f'This is our Current Price {current_price}$')
        print(f'This is our Target Price: {sellprice}$')
        print(f'this is our PNL percentage: {(perc)}%')

        pnl_close = False
        in_pos = False

        if perc > 0:

            print('we are in a winning position')
            if perc > target:
                print(f'^___^ starting the kill switch ! {target} % hit !')
                in_pos = True
                pnl_close = True
                logging.info(entry_price, sellprice, perc)
                kill_switch()
            else:
                in_pos = True
                pnl_close = False
                print('We have not hit our target yet!')

            return pnl_close, in_pos

        elif perc < 0:
            print('we are in a losing position but holding on...')
            in_pos = True
            if perc < risktolerance:
                pnl_close = True
                kill_switch()



            return pnl_close, in_pos, size, long

    except:
        print('Not in position')

        pnl_close = False
        in_pos = False

        return pnl_close, in_pos

    #return in_pos

def bot():

    pnl_close() #checking if we hit pnl

    df_d = daily_sma() # determines long/short
    df_f = f15_sma() # provides prices bp_1, bp_2, sp_1, sp_2
    ask = ask_bid()[0]
    bid = ask_bid()[1]

    # MAKE OPEN ORDER
    # LONG OR SHORT?
    sig = df_d.iloc[-1]['sig']
    #print(sig)

    open_size = pos_size/2

    # only run if not in position
    in_pos = pnl_close()[1]
    if in_pos == False:

        try:

            if sig == 'BUY':
                print('make an  order as a BUY')
                bp_1 =  df_f.iloc[-1]['bp_1']
                bp_2 = df_f.iloc[-1]['bp_2']
                print(f'this bp_1: {bp_1} this is bp_2: {bp_2}')
                print('____________________________________________')
                kucoin.cancel_all_orders(symbol)
                kucoin.create_limit_buy_order(symbol, open_size, bp_1, params)
                kucoin.create_limit_buy_order(symbol, open_size, bp_2, params)


            else:
                print('making an opening order as a SELL')
                sp_1 = df_f.iloc[-1]['sp_1']
                sp_2 = df_f.iloc[-1]['sp_2']
                print(f'this sp_1: {sp_1} this is sp_2: {sp_2}')
                kucoin.cancel_all_orders(symbol)
                kucoin.create_limit_sell_order(symbol, open_size, sp_1, params)
                kucoin.create_limit_sell_order(symbol, open_size, sp_2, params)

        except:
            print('+NOT ENOUGH FUNDS FOR ORDER+')

    else:

        print('we are in position already, not creating new orders right now..')

# Bootstrap by getting the most recent time that had minutes as a multiple of 5
time_now = datetime.utcnow()  # Or .now() for local time
prev_minute = time_now.minute - (time_now.minute % 1)
time_rounded = time_now.replace(minute=prev_minute, second=0, microsecond=0)

while True:
    try:
        # Wait until next 1 minute time
        time_rounded += timedelta(minutes=1/2)
        time_to_wait = abs((time_rounded - datetime.utcnow()).total_seconds())
        time.sleep(time_to_wait)

        # Now do whatever you want
        bot()
    except:
        time.sleep(45)

        time_rounded += timedelta(seconds=30)
        time_to_wait = abs((time_rounded - datetime.utcnow()).total_seconds())
        time.sleep(time_to_wait)

        # Now do whatever you want
        bot()
