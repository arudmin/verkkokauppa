# -*- coding: utf-8 -*-
import redis
import requests
import telebot
import os, re, sys, urllib
import time, pytz, locale
import jsonpickle, json
import botan
import math
import html

try:
    from urllib.parse import urlparse
except ImportError:
     from urlparse import urlparse

from datetime import datetime, date
from telebot import types
from googletrans import Translator
from pytz import timezone, utc
import xml.etree.ElementTree as xml

if sys.version[0] == '2':
    reload(sys)
    sys.setdefaultencoding('utf-8')

botan_token = os.environ['BOTAN_TOKEN']

r = redis.from_url(os.environ["REDIS_URL"], charset="utf-8", decode_responses=True)

bot = telebot.TeleBot(os.environ['TELEGRAM_TOKEN'])
# bot = telebot.AsyncTeleBot(os.environ['TELEGRAM_TOKEN'])

translator = Translator()

plural_goods = ["товар", "товара", "товаров"]

tz_fin = timezone('Europe/Helsinki')
tz_rus = timezone('Europe/Moscow')

# markup_start = types.ReplyKeyboardMarkup()
# markup_start.row('инфо о товаре', 'избранное')
# markup_start.row('на границе', 'магазины', 'справка')
# bot.send_message(message.chat.id, "", reply_markup=markup)

# class Object:
#     def toJSON(self):
#         return json.dumps(self, default=lambda o: o.__dict__,
#             sort_keys=True, indent=4)

kb_start = [
    'Поиск',
    '⭐Избранное',
    '🔥Акции',
    'Таможня',
    'Справка',
]
# kb_start = [
#     '🔎 Поиск', '⭐ Избранное', '🔥 Акции', '📸 Таможня', '💡 Справка', '🇫🇮🇺🇸🇷🇺 Справка'
# ]

api_url = 'https://verkcom.herokuapp.com'

cameras_api_fi = 'https://tie.digitraffic.fi/api/v1/data/camera-data/'
cameras_url_fi = 'https://weathercam.digitraffic.fi/'
cameras_id_fi  = {
    'svet' : 'C03508', # Светогорск → Иматра
    'brus' : 'C03510', # Брусничное → Нуямаа
    'torf' : 'C03512'  # Торфяновка → Ваалимаа
}
cameras_caption_fi = {
    'svet': "Иматры → Светлогорск",
    'brus': "Нуямаа → Брусничное",
    'torf': "Ваалима → Торфяновка",
}
kb_customs = {
    'svet' : 'Светогорск – Иматра',
    'brus' : 'Брусничное – Нуямаа',
    'torf' : 'Торфяновка – Ваалимаа',
    # 'lutt' : 'Люття - Вартиус',
    # 'niir' : 'Ниирала / Вяртсиля',
}
kb_extra = {
    'extra_default' : 'Основной каталог',
    'extra_raisio' : 'Акции в Райсио'
}


# return currency exchange CUR to RUB
def get_cur(cur='eur'):
    cur_id = {'eur': 'R01239', 'usd': 'R01235'}
    api_url = "http://www.cbr.ru/scripts/XML_daily.asp"
    r = requests.get(api_url)
    tree = xml.fromstring(r.text)
    # print(r.text)
    return tree.find(".//Valute[@ID='%s']/Value" % cur_id[cur]).text.replace(',', '.')

cur_ru = float(get_cur())


fav_list = ["⭐ Сохранить", "⭐ Удалить"]
bot_name = bot.get_me().username

#раздел Справка
def info(message):
    botan_send(message)
    msg  = msg_info % (is_shop_opened('helsinki'), is_shop_opened('raisio'), is_shop_opened('pirkkala'), is_shop_opened('oulu'), is_shop_opened('vantaa'))
    keyboard = pages_reply_keyboard(kb_start, True)
    bot.send_message(chat_id=message.chat.id, text=msg, parse_mode='Markdown', reply_markup=keyboard, disable_web_page_preview=True)

    # keyboard = ✅ 💚 ❤️ 🔴 pages_reply_keyboard(kb_start)
    # bot.send_message(message.chat.id, "Выберите пункт меню", parse_mode='Markdown', reply_markup=keyboard)


#раздел Избранное
def favorites(message, counter = 1):
    user_id = message.from_user.id
    redis_key = "users:%s:%s" % (user_id, 'favorite')
    fav_data = r.hgetall(redis_key)
    keyboard = pages_reply_keyboard(kb_start, True)

    if not fav_data:
        msg = "У вас нет сохраненных товаров."
        bot.send_message(chat_id=message.chat.id, text=msg, reply_markup=keyboard)
        return 0

    count = len(fav_data)
    msg = "В вашем списке %d %s" % (count, get_plural(count, ['товар','товара','товаров']))
    bot.send_message(chat_id=message.chat.id, text=msg, reply_markup=keyboard)

    for sku, sku_name in fav_data.items():
        msg = "*%d* %s" % (counter, sku_name)
        kb_fav = {'fav:%s' % sku : fav_list[1]}
        kb_fav.update({'sku:%s' % sku: 'Подробнее'})
        keyboard = pages_inline_keyboard(kb_fav)
        bot.send_message(chat_id=message.chat.id, text=msg, reply_markup=keyboard, parse_mode = 'Markdown')
        counter += 1
    return 0


# функционал вывода изображения с камер на границах
def customs(message):
    # for k,v in cameras_id_fi.items():
    keyboard = pages_inline_keyboard(kb_customs, True)
    bot.send_message(chat_id=message.chat.id, text="Вы можете посмотреть дорожную обстановку на границе с Финляндией около различных пунктов пропуска.\nВыберите направление:", parse_mode='Markdown', reply_markup=keyboard)
    return 0


# обработка поискового запроса на сайте веркки
def search_items(message):
    # print(message)
    query = message.text

    botan_send(message)
    log_search(message.from_user.id, query)

    if len(query) < 4:
        bot.send_message(message.chat.id, '🔴 Слишком короткий запрос. Введите хотя бы четыре символа для поиска по товарам на сайте.')
        return 0

    reply = bot.send_message(message.chat.id, '🔎 Ищу товары по запросу _\"%s\"_. Пожалуйста, подождите.'% query, parse_mode='Markdown')
    r = requests.get('%s/search/%s'% (api_url, query))

    if (r.status_code != 200):
        msg = '🔴 Не найдены товары по запросу _\"%s\"_. Введите другой поисковый запрос. Например _\"iphone 8 256\"_, или _\"56530\"_'% query

        bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text=msg, parse_mode='Markdown')
        return 0

    items = r.json()
    items_on_page = 9
    p = lambda x: '{:,.0f}'.format(x).replace(',', ' ')
    # msg  = "_✅ Показаны %d %s из %d_\n\n" % (items_on_page, get_plural(items_on_page, plural_goods), items['items_count'])
    # msg  = "_✅ Результат: %d %s_\n\n" % (items['items_count'], get_plural(items_on_page, plural_goods))
    msg  = "_✅ Результаты по запросу  \"%s\"_\n\n" % query
    for key, item in items['items'].items():
        msg += "*%s*\n" % item['sku_name']
        # msg += "%s *%s*\n" % (key, item['sku_name'])
        # try:
        #     sku_price = int(item['sku_price'])
        # except:
        sku_price = get_price(item['sku_price'])
        # sku_price = str(item['sku_price']).rstrip('0.')
        msg += "%s\n"  % sku_price
        msg += "↑ Информация о товаре /sku%s\n" % item['sku_id']
        msg += "\n"
        if int(key) > items_on_page:
            break

    # keyboard = pages_reply_keyboard(kb_start, True)
    bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text=msg[0:3999], parse_mode='Markdown')
    # bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text='ok', parse_mode='Markdown')

    # reply = bot.send_message(message.chat.id, "Введите код товара")
    # bot.register_next_step_handler(reply, after_start)
    # bot.send_message(message.chat.id, "Посмотреть товар на сайте", reply_markup=keyboard)
    return 0


#рездел Таможня (фотографии с границы)
@bot.callback_query_handler(func=lambda call: call.data in kb_customs)
def callback_customs(call):

    botan_send(call.message, kb_customs[call.data])
    # http://wap.megafonpro.ru/is3nwp/wc_2/img.jsp?path=/var/IS3NWP/ftp_mnt/webcams/torfynovka/2018-01-28/IPCam133038/1/20_02_17.jpg
    # http://wap.megafonpro.ru/is3nwp/wc_2/img.jsp?path=/var/IS3NWP/ftp_mnt/webcams/svetogorsk/Schedule/20180323/03272101.jpg

    camera_url  = cameras_api_fi + cameras_id_fi[call.data]
    camera_data = requests.get(camera_url).json()['cameraStations']
    camera_measured_time = camera_data[0]['cameraPresets'][0]['measuredTime']
    try:
        dt = datetime.strptime(camera_measured_time.replace('+03:00','+0300'), '%Y-%m-%dT%H:%M:%S%z')
    except:
        return 0

    photo_time = dt.astimezone(tz_rus)
    rus_time   = datetime.now().astimezone(tz_rus)
    time_delta = (((rus_time-photo_time).seconds//60)%60)
    photo_url = cameras_url_fi+cameras_id_fi[call.data]+"02.jpg?time="+"{:%d%m%Y%H%M%S}".format(photo_time)

    msg  = "🇫🇮[ ](%s)Камера наблюдения на финской границе со стороны %s.\n" % (photo_url, cameras_caption_fi[call.data])
    if time_delta:
        msg += "Фото получено %s мин назад в %s (МСК)" % (time_delta, "{:%H:%M}".format(photo_time))
    else:
        msg += "Фото получено с камеры только что, еще тепленькое 😄"
    # bot.send_message(call.message.chat.id, text=msg, parse_mode='Markdown', reply_markup=keyboard)
    if requests.get(photo_url).status_code != 200:
        msg = "🔴 Не удается получить данные с камеры, попробуйте еще раз."
    keyboard = pages_inline_keyboard(kb_customs, True)
    try:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=msg, parse_mode='Markdown', reply_markup=keyboard)
    except:
        pass
    return 0


# раздел Акции
@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('sales_page:') == 0)
def sales_default(message):
    # print('sales')
    seq, page, out = 7, 0, ''

    if hasattr(message, 'data') and message.data.find('sales_page:') == 0:
        page = int(message.data.replace('sales_page:',''))

    if hasattr(message, 'data'):
        message = message.message
    else:
        botan_send(message)

    # текущая позиция в списке товаров
    i = seq * page + 1

    #список ационных товаров
    extra_list = r.lrange('extra_list', 0, -1)

    for sku in pagination(extra_list, seq=seq, page=page):
        # print(sku)
        r_item = "items:%s:" % sku # set redis key for items
        name = r.get(r_item+'name') # get item name

        out += "*%d* [%s](https://t.me/%s?&start=%s)\n" % (i, name, bot_name, sku)
        i += 1
        if get_price(r.get(r_item+'price_old')):
            out += "Старая цена: %s\n" % get_price(r.get(r_item+'price_old'))
            out += "По акции: %s\n" % get_price(r.get(r_item+'price'))
        else:
            out += "Цена: %s\n" % get_price(r.get(r_item+'price'))

        out += "\n"

    msg  = "%sАкционные товары из еженедельного каталога http://verk.com/extra\n" % out

    last_page = math.ceil(len(extra_list)/seq)-1

    if len(extra_list) <= seq:
        kb_pagination = {}
    elif page == 0:
        kb_pagination = {'sales_page:1': 'след. страница'}
    elif page >= last_page:
        kb_pagination = {"sales_page:%d" % (page-1): '←'}
        msg += "Показано %d из %d.\n" % (i-1, len(extra_list))
    else:
        kb_pagination = {
            # "sales_page.%d" % (0): '«', #prev btn
            "sales_page:%d" % (page-1): '←', #prev btn
            "sales_page:%d" % (page+1): '→', #next btn
            # "sales_page.%d" % (last_page): '»', #next btn
        }
        msg += "Показано %d из %d.\n" % (i-1, len(extra_list))
        time.sleep(1)

    # msg += "%d из %d\n" % (page, math.ceil(len(extra_list)/seq)-1)
    msg += "После выбора товара нажмите `Начать` внизу.\n"

    keyboard = pages_inline_keyboard(kb_pagination)
    if page:
        # print(message.message_id)
        bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=msg, disable_web_page_preview=True, parse_mode='Markdown', reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, msg, disable_web_page_preview=True, parse_mode='Markdown', reply_markup=keyboard)
    return 0


def sales_raisio(message, i=0):
    if hasattr(message, 'data'):
        message = message.message
    else:
        botan_send(message)

    r = requests.get(api_url + '/raisio/json')
    extra_list = r.json()
    for item in extra_list:
        # if item sale date out of
        if item['expire']:
            continue

        description = translate(item['descriptionShort'])
        image_url   = item['image']
        price       = get_price(item['price'])
        name        = translate(item['name'], dest='en')
        # pid         = re.search(r'\d{6}', image_url)[0]
        pid         = item['pid']

        i += 1
        out  = "*%d*[ ](%s)[%s](https://t.me/%s?&start=pid_%s)\n" % (i, image_url, name, bot_name, pid)
        out += "Цена по акции: %s\n\n" % price
        out += "%s\n" % description
        # out += "Подробнее: /pid%s" % pid
        # out += "Старая цена: %s\n" % get_price(r.get(r_item+'price_old'))
        # out += "\n"
        bot.send_message(message.chat.id, out, parse_mode='Markdown')
        time.sleep(1)

    msg  = "Показаны актуальные товары со скидкой в Магазине Райсио. Список акционных товаров взят отсюда: https://verk.com/avajaiset\n"
    msg += "После выбора товара нажмите кнопку `Начать`"
    keyboard = pages_reply_keyboard(kb_start, True)
    bot.send_message(message.chat.id, msg, disable_web_page_preview=True, parse_mode='Markdown', reply_markup=keyboard)

    return 0


@bot.message_handler(commands=["start"])
def cmd_start(message):

    botan_send(message)

    r_user = 'users:%s' % message.from_user.id
    if not (r.exists(r_user+":id")):
        pipe = r.pipeline()
        chat = dict(vars(message.from_user))
        for k,v in chat.items():
            pipe.set("%s:%s"% (r_user, k), v)
        try:
            photo = bot.get_user_profile_photos(message.from_user.id).photos[0][0].file_id
        except:
            photo = ''

        pipe.set("%s:%s"% (r_user, 'profile_photo_id'), photo)
        pipe.set("%s:%s"% (r_user, 'created'), time.time())
        pipe.execute()

    keyboard = pages_reply_keyboard(kb_start, True)

    # check if command '/start' contains parameters and handle it
    if len(message.text.replace('/start','').strip()):
        query = message.text.replace('/start','').strip()
        reply = bot.send_message(message.chat.id, query, reply_markup=keyboard)

        if query.find('pid_') == 0:
            search_pid(reply)
        elif query.isdigit():
            search_sku(reply)
        else:
            search_items(reply)
        return 0

    reply = bot.send_message(message.chat.id, "Выберите пункт меню", reply_markup=keyboard)
    # bot.register_next_step_handler(reply, after_start)
    return 0


@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('pid:') == 0)
@bot.message_handler(func = lambda call: call.content_type == 'text' and hasattr(call, 'text') and call.text.find('/pid')==0)
@bot.message_handler(func = lambda call: hasattr(call, 'text') and call.text.find('pid_')==0)
def search_pid(message):
    # if hasattr(message, 'text') and message.text.isdigit():
        # pid = message.text
    if hasattr(message, 'data'):
        pid = message.data[4:]
        message = message.message
    else:
        pid = message.text[4:]
    print(message.text)

    botan_send(message, pid)

    chat_id = message.chat.id

    bot.send_chat_action(chat_id, 'typing')

    r = requests.get('%s/pid/%s'% (api_url, pid))

    if (r.status_code != 200):
        keyboard = pages_reply_keyboard(kb_start)
        msg = '🔴 Товар не найден. Введите другой поисковый запрос. Например _\"iphone 8 256\"_, или _\"56530\"_'
        bot.send_message(message.chat.id, msg, reply_markup=keyboard, parse_mode='Markdown')
        return 0

    item = r.json()

    # save request to log in redis
    # log_search(user_id=message.chat.id, sku=item['_sku'])
    # item_name = item['name']
    sku = item['_sku']

    message.text = sku

    search_sku(message)
    # msg = item_name
    # kb_sku = {
        # 'favorite:%s' % sku : fav_list[is_fav(user_id, sku)] ,
        # 'more_info:%s'%sku : 'Полная информации о товаре',
        # item['_url'] : 'Посмотреть товар на сайте',
    # }
    # keyboard = pages_inline_keyboard(kb_sku, True)
    # reply = bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text=msg, parse_mode = 'Markdown', reply_markup=keyboard)

    return 0


# Handle EXTRAS inline cllback
@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('extra_') == 0)
def choose_extra(message):
    bot.edit_message_text(chat_id=message.message.chat.id, message_id=message.message.message_id, text='Загружается список акционных товаров. Пожалуйста, подождите.', parse_mode = 'Markdown')
    if message.data == next(iter(kb_extra)): # if default extras
        sales_default(message)
    else: # if Raisio extras
        sales_raisio(message)
    return 0


@bot.message_handler(func = lambda call: call.content_type == 'text' and call.text.isdigit())
@bot.message_handler(func = lambda call: call.content_type == 'text' and hasattr(call, 'text') and call.text.find('/sku')==0)
@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('sku:') == 0)
def search_sku(message):
    # print(message)
    if hasattr(message, 'text') and message.text.isdigit():
        sku = message.text
    elif hasattr(message, 'data'):
        sku = message.data[4:]
        message = message.message
    else:
        sku = message.text[4:]

    botan_send(message, sku)
    user_id = message.chat.id

    # reply = bot.send_message(message.chat.id, 'Загружаются данные по коду товара %s. Пожалуйста, подождите.' % sku)
    reply = bot.send_message(message.chat.id, 'Загружаются данные, пожалуйста, подождите.')
    r = requests.get('%s/sku/%s'% (api_url, sku))

    if (r.status_code != 200):
        msg = '🔴 Товар с кодом _\"%s\"_ не найден. Введите другой поисковый запрос. Например _\"iphone 8 256\"_, или _\"56530\"_' % sku
        reply = bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text=msg, parse_mode = 'Markdown')
        return

    item = r.json()

    # save request to log in redis
    log_search(user_id=message.chat.id, sku=item['_sku'])

    highlights = ''
    if item['highlights']:
        for i in item['highlights']:
            highlights += "• %s\n" % i
        highlights += "\n"

    item_name = item['name']
    item_picture = item['images'][0]

    price = "Цена: %s\n" % get_price(r.json()['price'])
    price_tax = "Инвоис: %s\n" % get_price(r.json()['price_vat'])
    price_export = "На экспорт: %s\n" % get_price(r.json()['price_export'])

    avail = translate(r.json()['avail_helsinki'].replace(' pv', ' дн.')).replace('немедленно', 'в наличии')
    availible_helsinki = "Наличие в Хельсинки: %s\n" % avail

    # формируем выдачу информации о товаре
    msg  = "*%s*[ ](%s)\n" % (item_name, item_picture)
    msg += highlights
    msg += price + price_export + price_tax

    try:
        weight = str(item['package_weight']) or ""
        msg += "\nВес Брутто: %s кг\n" % weight.rstrip('0.')
    except:
        pass
    msg += availible_helsinki
    msg += "Код товара: [%s](https://t.me/%s?&start=%s)" % (sku, bot_name, sku)

    kb_sku = {
        'favorite:%s' % sku : fav_list[is_fav(user_id, sku)] ,
        # 'more_info:%s'%sku : 'Полная информации о товаре',
        item['_url'] : 'Посмотреть товар на сайте',
    }
    keyboard = pages_inline_keyboard(kb_sku, True)


    reply = bot.edit_message_text(chat_id=reply.chat.id, message_id=reply.message_id, text=msg, parse_mode = 'Markdown', reply_markup=keyboard)

    # bot.register_next_step_handler(reply, update_inline_keyboard)

    return 0


@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('favorite:') == 0)
def update_item_inline_keyboard(call):
    # print(call)
    sku = call.data.split(':')[1]
    user_id = call.from_user.id
    url = 'https://www.verkkokauppa.com/fi/product/%s' % sku
    kb_item = {
        # 'more_info:%s'%sku : 'Больше информации о товаре',
        url : 'Посмотреть товар на сайте',
    }

    kb_fav = change_fav_status(user_id, sku, 'favorite')
    kb_fav.update(kb_item)
    keyboard = pages_inline_keyboard(kb_fav, True)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    return 0


@bot.callback_query_handler(func=lambda call: hasattr(call, 'data') and call.data.find('fav:') == 0)
def update_fav_inline_keyboard(call):
    # print(call)
    sku = call.data.split(':')[1]
    user_id = call.from_user.id
    kb_fav = change_fav_status(user_id, sku, 'fav')
    kb_fav.update({'sku:%s'%sku:'Подробнее'})
    keyboard = pages_inline_keyboard(kb_fav)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)

    return 0


@bot.message_handler(content_types=["photo"])
def get_photo(message):
    print(message)
    bot.send_message(message.chat.id, "Супер, но я пока не умею искать по фото ¯\_(ツ)_/¯")
    return 0


@bot.message_handler(content_types=["text"])
def repeat_all_messages(message):
    botan_send(message)

    if message.text == "⭐Избранное":
        favorites(message)

    elif message.text == "Поиск":
        photo = 'AgADAgADOakxGxYTyUjSz5EIv2XCdAa4mg4ABGMiE4-7QWB8_f8BAAEC'
        reply = bot.send_photo(message.chat.id, photo, 'Введите название товара для поиска, или его код с сайта verkkokauppa.com.')

    elif message.text == "🔥Акции":
        keyboard = pages_inline_keyboard(kb_extra, True)
        msg = 'Выберите каталог с акциями'
        # msg = bot.reply_to(message, 'How old are you?', reply_markup=keyboard)
        reply = bot.send_message(message.chat.id, text=msg, reply_markup=keyboard)
        # bot.register_next_step_handler(reply, choose_extra)

    elif message.text == "Таможня":
        customs(message)

    elif message.text == "Справка":
        info(message)

    else:
        search_items(message)

    return 0


def is_fav(user_id, sku):
    redis_key = "users:%s:%s" % (user_id, 'favorite')
    return sku in r.hkeys(redis_key)

def change_fav_status(user_id, sku, kb):
    # set redis key for fav items
    redis_key = "users:%s:%s" % (user_id, 'favorite')
    if is_fav(user_id, sku):
        r.hdel(redis_key, sku)
        return {'%s:%s'%(kb, sku) : fav_list[0]}
    else:
        sku_name = get_sku_param(sku, 'name')
        r.hset(redis_key, sku, sku_name)
        return {'%s:%s'%(kb, sku) : fav_list[1]}

def botan_send(message, custom_event=None):
    try:
        uid = message.from_user
        message_json = jsonpickle.encode(message)
        message_dict = json.loads(message_json)
        if custom_event:
            b = botan.track(botan_token, uid, message_dict, custom_event)
        else:
            b = botan.track(botan_token, uid, message_dict, message.text)
        # print(b)
    except:
        return 0

    # print(message.text)
    # short_url = botan.shorten_url(original_url, botan_token, uid)
    return b

def is_shop_opened(shop):
    work_time = { # 0: Monday, 1: Tuesday... 6: Sunday
        'helsinki': {0:'9-21',1:'9-21',2:'9-21',3:'9-21',4:'9-21',5:'9-21',6:'11-19'},
        'raisio': {3:'8-21',4:'9-21',5:'9-19',6:'11-19'},
        'pirkkala': {0:'9-21',1:'9-21',2:'9-21',3:'9-21',4:'9-21',5:'9-19',6:'11-19'},
        'oulu': {0:'9-21',1:'9-21',2:'9-21',3:'9-21',4:'9-21',5:'9-19',6:'11-19'},
        'vantaa': {0:'9-21',1:'9-21',2:'9-21',3:'9-21',4:'9-21',5:'9-18',6:'12-18'},
    }
    fin_time = datetime.now().astimezone(tz_fin)
    day_num  = fin_time.weekday()
    hour_num = fin_time.hour
    is_opened_symbol = {True: '✅', False: '☑️'}
    try:
        work_hours = (work_time[shop][day_num]).split('-')
        if int(work_hours[0]) <= hour_num and hour_num < int(work_hours[1]):
            return is_opened_symbol[True]
        else:
            return is_opened_symbol[False]
    except:
        return is_opened_symbol[False]

def is_url(url):
    return urlparse(url).scheme != ""

def get_sku_param(sku, param):
    redis_key = 'items:%s:%s' % (sku, param)
    value = r.get(redis_key)
    if value:
        return value

    result = requests.get('%s/sku/%s'% (api_url, str(sku)))

    try:
        return result.json()[str(param)]
    except:
        return 0

def pagination(mylist, seq=5, page=0):
    sorted_list = [mylist[i:i+seq] for i in range(0, len(mylist), seq)]
    if page > len(sorted_list):
        return
    # if not page:
        # r.set('tmp:%s:page' % 'user_id', page)
    return sorted_list[page]

def pages_reply_keyboard(m, rk=True, ot=False):
    kb_start = types.ReplyKeyboardMarkup(resize_keyboard=rk, one_time_keyboard=ot)
    kb_start.add(*[types.KeyboardButton(name) for name in m])
    return kb_start

def pages_inline_keyboard(m, rows=False, ):
    keyboard = types.InlineKeyboardMarkup()
    btns = []
    if rows:
        for k, v in m.items():
            if is_url(k):
                keyboard.row(types.InlineKeyboardButton(text=v, url=k))
            else:
                keyboard.row(types.InlineKeyboardButton(text=v, callback_data=k))
    else:
        for k, v in m.items():
            if is_url(k):
                btns.append(types.InlineKeyboardButton(text=v, url=k))
            else:
                btns.append(types.InlineKeyboardButton(text=v, callback_data=k))
        keyboard.add(*btns)
    return keyboard # возвращаем объект клавиатуры

#перевод строки
def translate(text='', src='fi', dest='ru'):
    return translator.translate(text, dest=dest, src=src).text

#сохранение лог-данных в базу редис
def log_search(user_id, sku):
    if user_id != 1293994:
        return r.zadd('search_history:%d'%user_id, str(sku), int(time.time() * 1000))
    return 0

# форматирует цену
def get_price(price):
    price = str(price).replace(',', '.')
    try:
        p = lambda x: '{:,.0f}'.format(x).replace(',', '')
        return "%s € ≈ %s ₽" % (str(price).rstrip('0.'), p(round(int(float(price)*cur_ru), -2)))
    except:
        return 0

# склоение числительных существительных
# x = числительное
# y = список формата ['товар', 'товара', 'товаров']
def get_plural(x, y):
    inumber = int(x) % 100
    if inumber >= 11 and inumber <=19:
        y = y[2]
    else:
        iinumber = inumber % 10
        if iinumber == 1:
            y = y[0]
        elif iinumber == 2 or iinumber == 3 or iinumber == 4:
            y = y[1]
        else:
            y = y[2]
    # return str(x) + " " + y
    return y

msg_info = \
"""
_✅ - открыто, ☑️ - закрыто_
_указано финское время (на час назад по МСК)_\n
%s [Хельсинки](https://www.verkkokauppa.com/fi/myymalat/jatkasaari): Tyynenmerenkatu 11, Helsinki 00220 ([карта](https://www.google.com/maps/place/Verkkokauppa.com/@60.156381,24.920937,12z/data=!4m5!3m4!1s0x0:0x749d95094ad5151a!8m2!3d60.1563809!4d24.9209373?hl=ru-RU)).
Режим работы:
пн–cб 9-21, вс 11–19.
*Только в Хельсинки!* Русскоязычные менеджеры работают каждый день в отделе _\"Экспорт и такс-фри\"_. Отдел находится на втором этаже рядом с кафе.\n
%s [Райсио](https://www.verkkokauppa.com/fi/myymalat/raisio): Kuloistentie 3, Raisio 21280 ([карта](https://www.google.com/maps/place/Verkkokauppa.com+Raisio/@60.493824,22.209485,12z/data=!4m5!3m4!1s0x0:0x5eda6865b57a4be6!8m2!3d60.4894269!4d22.2089705?hl=ru-RU)).
Режим работы:
пн–ср: закрыт, чт 8–21, пт 9–21, cб 9–19, вс 11–19.\n
%s [Пирккала](https://www.verkkokauppa.com/fi/myymalat/pirkkala): Saapastie 2, Pirkkala 33950 ([карта](https://www.google.com/maps/place/Verkkokauppa.com+Pirkkala/@61.467846,23.721438,11z/data=!4m5!3m4!1s0x0:0x172884afda629991!8m2!3d61.4678461!4d23.7214385?hl=ru-RU)).
%s [Оулу](https://www.verkkokauppa.com/fi/myymalat/oulu): Kaakkurinkulma 4, Oulu 90410 ([карта](https://www.google.com/maps/place/Verkkokauppa.com+Oulu/@64.962615,25.520144,10z/data=!4m5!3m4!1s0x0:0x85238d9563366ae6!8m2!3d64.9626147!4d25.5201444?hl=ru-RU)).
Режим работы магазинов:
пн–пт 9–21, cб 9–19, вс 11–19.\n
%s [Вантаа](https://www.verkkokauppa.com/fi/noutovarastot/vantaa): Tuupakantie 32, Vantaa 01740 ([карта](https://www.google.com/maps/place/Verkkokauppa.com+Vantaan+noutovarasto/@60.295053,24.9123,11z/data=!4m5!3m4!1s0x0:0x69d011955bc7f4cd!8m2!3d60.2950535!4d24.9123004?hl=ru-RU)).
Режим работы склада:
пн-пт 9-21, сб 9–18, вс 12–18.\n
🔗 Официальная группа в [ВКонтакте](https://vk.com/verkkokauppa_com)
📧 Эл. почта (отвечают по-русски): russki@verk.com
"""

bot.polling(none_stop=True)

# if __name__ == '__main__':
#     bot.polling(none_stop=True)
