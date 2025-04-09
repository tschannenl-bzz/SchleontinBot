import threading
import time
import socket
import traceback
import io
import json
import selectors
import struct
import sys

import uuid
from datetime import datetime


from typing import List, Optional

import game.cards
from game.cards import Card, CardType

hostname = socket.gethostname()
IPAddr = socket.gethostbyname(hostname)

HOST = '127.0.0.1'
PORT = 65432


class Message:
    """
    constructor for super-class
    """
    def __init__(self, selector, socket, ipaddr):
        self._selector = selector
        self._socket = socket
        self._ipaddr = ipaddr
        self._event = ''
        self._recv_buffer = b''
        self._send_buffer = b''
        self._request = None
        self._jsonheader_len = None
        self._jsonheader = None

    def process_events(self, mask):
        """
        process the events
        :param mask:
        :return:
        """
        if mask & selectors.EVENT_READ:
            self._process_read()
        if mask & selectors.EVENT_WRITE:
            self._process_write()

    def set_selector_events_mask(self, mode):
        """
        Set selector to listen for events: .
        :param mode: mode is 'r', 'w', or 'rw'
        :return:
        """
        if mode == 'r':
            events = selectors.EVENT_READ
        elif mode == 'w':
            events = selectors.EVENT_WRITE
        elif mode == 'rw':
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f'Invalid events mask mode {mode!r}.')
        self._selector.modify(self._socket, events, data=self)

    def _process_headers(self):
        """
        process the protocol and json headers
        :return:
        """
        self._event = 'READ'
        self._read()

        if self._jsonheader_len is None:
            self._process_protoheader()

        if self._jsonheader_len is not None:
            if self._jsonheader is None:
                self._process_jsonheader()

    def _process_read(self):
        """
        dummy implementation must be implemented in the child class
        :return:
        """
        raise NotImplementedError

    def _read(self):
        """
        reads the data from the socket
        :return: None
        """
        try:
            data = self._socket.recv(4096)
        except BlockingIOError:
            pass
        else:
            if data:
                self._recv_buffer += data
            else:
                raise RuntimeError('Peer closed.')

    def _create_response_json_content(self):
        content_encoding = 'utf-8'
        content = json_encode(self._response, content_encoding)

        response = {
            'content_bytes': content,
            'content_type': 'text/json',
            'content_encoding': content_encoding,
        }

        return response

    def _create_response_text_content(self):
        """
        creates the response content as text
        :return: dict
        """
        response = {
            'content_bytes': json_encode(self._response, 'utf-8'),
            'content_type': 'text/plain',
            'content_encoding': 'utf-8',
        }
        return response

    def _process_write(self):
        """
        dummy implementation must be implemented in the child class
        :return:
        """
        raise NotImplementedError

    def _write(self):
        """
        sends the response to the client
        :return:
        """
        if self._send_buffer:
            print(f'Sending {self._send_buffer!r} to {self._ipaddr}')
            try:
                sent = self._socket.send(self._send_buffer)
            except BlockingIOError:
                pass
            else:
                self._send_buffer = self._send_buffer[sent:]
                if type(self).__name__ == 'ServerMessage' and \
                        sent and \
                        not self._send_buffer:
                    self._close()

    def _process_protoheader(self):
        """
        process the protocol header
        :return:
        """
        hdrlen = 2
        if len(self._recv_buffer) >= hdrlen:
            self._jsonheader_len = struct.unpack(
                '>H', self._recv_buffer[:hdrlen]
            )[0]
            self._recv_buffer = self._recv_buffer[hdrlen:]

    def _process_jsonheader(self):
        """
        process the json header
        :return:
        """
        hdrlen = self._jsonheader_len
        if len(self._recv_buffer) >= hdrlen:
            self._jsonheader = json_decode(
                self._recv_buffer[:hdrlen], 'utf-8'
            )
            self._recv_buffer = self._recv_buffer[hdrlen:]
            for reqhdr in (
                    'byteorder',
                    'content-length',
                    'content-type',
                    'content-encoding',
            ):
                if reqhdr not in self._jsonheader:
                    raise ValueError(f'Missing required header "{reqhdr}".')

    def _create_message(
            self,
            *,
            content_bytes,
            content_type,
            content_encoding
    ):
        """
        creates the encoded message to send to the client
        :param content_bytes:
        :param content_type:
        :param content_encoding:
        :return:
        """

        jsonheader = {
            'byteorder': sys.byteorder,
            'content-type': content_type,
            'content-encoding': content_encoding,
            'content-length': len(content_bytes),
        }
        jsonheader_bytes = json_encode(jsonheader, 'utf-8')
        message_hdr = struct.pack('>H', len(jsonheader_bytes))

        response_message = message_hdr + jsonheader_bytes + content_bytes
        return response_message

    def _close(self):
        """
        closes the connection
        """
        print(f'Closing connection to {self._ipaddr}')
        try:
            self._selector.unregister(self._socket)
        except Exception as e:
            print(
                f'Error: selector.unregister() exception for '
                f'{self._ipaddr}: {e!r}'
            )

        try:
            self._socket.close()
        except OSError as e:
            print(f'Error: socket.close() exception for {self._ipaddr}: {e!r}')
        finally:
            self._socket = None

    @property
    def ipaddr(self):
        return self._ipaddr

    @ipaddr.setter
    def ipaddr(self, value):
        self._ipaddr = value

    @property
    def event(self):
        return self._event

    @event.setter
    def event(self, value):
        self._event = value

    @property
    def request(self):
        return self._request

    @property
    def response(self):
        return self._response

    @response.setter
    def response(self, value):
        self._response = value


def json_encode(obj, encoding):
    """
    encodes the object as json
    :param obj: the object to encode
    :param encoding: the codec to use for encoding
    :return: String
    """
    return json.dumps(obj, ensure_ascii=False).encode(encoding)


def json_decode(json_bytes, encoding):
    """
    decodes json data into an object
    :param json_bytes: the json data to be decoded
    :param encoding: the codec to use for decoding
    :return: Object
    """
    text_io_wrap = io.TextIOWrapper(
        io.BytesIO(json_bytes), encoding=encoding, newline=''
    )
    obj = json.load(text_io_wrap)
    text_io_wrap.close()
    return obj

class Services:
    """
    manages a list of registered services
    """
    def __init__(self):
        """
        constructor for the Services class
        """
        self._service_list = []

    def register(self, type, ipaddr, port):
        """
        registers a service
        :param type: A keyword to define the type of service
        :param ipaddr: IPv4 or IPv6 address of the service
        :param port: Portnumber where the service can be reached
        :return: UUID identifying the service, must be supplied for 'heartbeat'
        """
        service_uuid = str(uuid.uuid4())
        service = {"uuid": service_uuid, "type": type, "ipaddr": ipaddr, "port": port, "timestamp": datetime.now()}
        self._service_list.append(service)
        return service_uuid
class ServerMessage(Message):
    """
    Class for the message from the server
    """
    def __init__(self, selector, socket, ipaddr):
        """
        constructor for the ServerMessage class
        """
        super().__init__(selector, socket, ipaddr)
        self._response = None
        self._response_created = False

    def _process_read(self):
        """
        process read-event
        :return:
        """
        self._process_headers()

        if self._jsonheader:
            if self._request is None:
                self._process_request()

    def _process_request(self):
        """
        process the request
        :return:
        """
        content_len = self._jsonheader['content-length']
        if not len(self._recv_buffer) >= content_len:
            return
        data = self._recv_buffer[:content_len]
        self._recv_buffer = self._recv_buffer[content_len:]
        if self._jsonheader['content-type'] == 'text/json':
            encoding = self._jsonheader['content-encoding']
            self._request = json_decode(data, encoding)
            print(f'Received request {self._request!r} from {self._ipaddr}')
        else:
            self._request = data
            print(
                f"Received {self._jsonheader['content-type']} "
                f'request from {self._ipaddr}'
            )

    def _process_write(self):
        """
        process the write-event
        :return:
        """
        self._event = 'WRITE'
        if self._request:
            if not self._response_created:
                self._create_response()

        self._write()

    def _create_response(self):
        """
        creates the response to the client
        :return:
        """
        if self._request['action'] == 'query':
            data = self._create_response_json_content()
        else:
            data = self._create_response_text_content()
        output = self._create_message(**data)
        self._response_created = True
        self._send_buffer += output

class ClientMessage(Message):
    """
    constructor for ClientMessage
    """
    def __init__(self, selector, socket, ipaddr, request):
        """
        constructor for the ClientMessage class
        """
        super().__init__(selector, socket, ipaddr)
        self._request = request
        self._request_queued = False
        self._response = None

    def _process_read(self):
        """
        process read-event
        :return:
        """
        self._process_headers()

        if self._jsonheader:
            if self._response is None:
                self.process_response()

    def _process_response_json_content(self):
        """
        process the response content
        :return:
        """
        content = self._response
        print(f'Got result: {content}')

    def _process_response_binary_content(self):
        """
        process binary content in the response
        :return:
        """
        content = self._response
        print(f'Got response: {content!r}')

    def _process_write(self):
        """
        process the write-event
        :return:
        """
        self._event = 'WRITE'
        if not self._request_queued:
            self._queue_request()

        self._write()

        if self._request_queued:
            if not self._send_buffer:
                self.set_selector_events_mask('r')

    def _queue_request(self):
        """
        queues up the request to be sent
        :return:
        """
        content = self._request['content']
        content_type = self._request['type']
        content_encoding = self._request['encoding']
        if content_type == 'text/json':
            req = {
                'content_bytes': json_encode(content, content_encoding),
                'content_type': content_type,
                'content_encoding': content_encoding,
            }
        else:
            req = {
                'content_bytes': content,
                'content_type': content_type,
                'content_encoding': content_encoding,
            }
        message = self._create_message(**req)
        self._send_buffer += message
        self._request_queued = True

    def process_response(self):
        """
        Process the response from the server
        :return:
        """
        content_len = self._jsonheader['content-length']
        if not len(self._recv_buffer) >= content_len:
            return
        data = self._recv_buffer[:content_len]
        self._recv_buffer = self._recv_buffer[content_len:]
        if self._jsonheader['content-type'] == 'text/json':
            encoding = self._jsonheader['content-encoding']
            self._response = json_decode(data, encoding)
            print(f'Received response {self.response!r} from {self._ipaddr}')
            self._process_response_json_content()
        else:
            # Binary or unknown content-type
            self._response = data
            print(
                f'Received {self._jsonheader["content-type"]} '
                f'response from {self._ipaddr}'
            )
            self._process_response_binary_content()
        self._close()

class SchleontinBot:
    """
    This is a helper class to run the bot in the local environment.
    The name MUST match the filename.
    """
    def __init__(self, name):
        self.name = name
        self._bot = SchleontinKitten(name)


    def request(self, data):
        """
        Request for a response
        :param data:
        :return:
        """
        if isinstance(data, dict):
            payload = data
        else:
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return "NONE"
        action = payload['action']
        if action == 'PLAY':
            return self._bot.play()
        elif action == 'START ':
            return 'ACK'
        elif action == 'DRAW':
            self._bot.add_card(payload['card'])
            return 'ACK'
        elif action == 'INFORM':
            return self._bot.inform(payload)
        elif action == 'DEFUSE':
            decksize = len(payload['decksize'])
            pos = self._bot.defuse_action(decksize)
            return pos

        elif action == 'FUTURE':
            self._bot.see_the_future(payload)
            return 'ACK'
        return None

class SchleontinKitten:
    def __init__(self, name):
        self.name = name
        self.hand = []
        self.exploding_kitten_count = 0
        self.next_kitten_index = None
        self.top_three = []
        self.placed_kitten_index = None
        self.cards_drawn_last = 0

    def play(self) -> Optional[Card]:
        """
        Entscheidet, ob eine Karte gespielt wird und welche.
        """
        # 1. Wenn Kitten ganz oben liegt (durch see_the_future oder defuse):
        danger_top = self.next_kitten_index == 0 or self.placed_kitten_index == 0


        if danger_top:
            for card in self.hand:
                if card.card_type == CardType.SKIP:
                    return card
            for card in self.hand:
                if card.card_type == CardType.SHUFFLE:
                    return card

        if not self.top_three and self._has_card(CardType.SEE_THE_FUTURE):
            return self._play_card(CardType.SEE_THE_FUTURE)

        if len(self.hand) >= 6:
            for card in self.hand:
                if card in [CardType.SKIP, CardType.SHUFFLE]:
                    return card

        return None

    def see_the_future(self, top_three: List[Card]) -> None:
        self.top_three = top_three
        self.next_kitten_index = None
        for i, card in enumerate(top_three):
            if card == CardType.EXPLODING_KITTEN:
                self.next_kitten_index = i
        self.placed_kitten_index = None

    def inform(self, state):
        deck_history = state.get("history_of_played_cards", [])
        self.exploding_kitten_count = deck_history.count("EXPLODING_KITTEN")

        kittens_left = max(0, 2 - self.exploding_kitten_count)
        remaining_cards = state.get("cards_left_to_draw", 0)
        self.next_kitten_index = None

        if kittens_left > 0 and remaining_cards > 0:
            risk = kittens_left / remaining_cards
            if risk > 0.4:
                self.next_kitten_index = 0

        self.cards_drawn_last = state.get("cards_drawn", 0)


    def add_card(self, card):
        self.hand.append(card)

    def defuse_action(self, decksize:int):

        if decksize >= 5:
            position = decksize - 2
        else:
            position = decksize - 1
        self.placed_kitten_index = position
        return position

    def _has_card(self, card_type):
        return any(card_type == game.cards.CardType for card_type in self.hand)

    def _play_card(self, card_type):
        for card in self.hand:
            if card.card_type == card_type:
                return card
        return None


def main():
    """
    main function for the socket-controller
    :return:
    """
    services = Services()
    bot = SchleontinBot(name="SchleontinKitten")

    message = send_request({
        "action":"MEOW",
        "ip": IPAddr,
        "name": "SchleontinKitten",
        "type": 'bot'
    })



    play = threading.Thread(target=swish_tail)
    play.daemon = True
    play.start()
    open_port(bot, message.response, services)

    # register the bot with the clowder => you get a port number
    # open a socket with the port number
    # listen for incoming connections from the arena

    # analyse the incoming connections
    # call the relevant bot method depending on the action
    # send the response back to the arena

    # close the socket

def swish_tail():
    try:
        while True:
            try:
                msg = send_request({
                    "action": "SWISH",
                    "name": "SchleontinBot",
                })
                time.sleep(10)
            except:
                return "something bad happened"
    except KeyboardInterrupt:
        print('Caught keyboard interrupt, exiting')



def open_port(bot, port, services):
    """
    main entry point for the discovery service
    """
    sel = selectors.DefaultSelector()

    lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Avoid bind() exception: OSError: [Errno 48] Address already in use
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((IPAddr, int(port)))
    lsock.listen()
    print(f'Listening on {(IPAddr, int(port))}')
    lsock.setblocking(False)
    sel.register(lsock, selectors.EVENT_READ, data=None)

    try:
        while True:
            events = sel.select(timeout=None)
            for key, mask in events:
                if key.data is None:
                    accept_wrapper(sel, key.fileobj)
                else:
                    message = key.data
                    try:
                        message.process_events(mask)
                        process_action(message, services)
                        response = bot.request(message._request)
                        message.response = response
                        if message._socket:
                            message.set_selector_events_mask("w")
                    except Exception:
                        print(
                            f'Main: Error: Exception for {message.ipaddr}:\n'
                            f'{traceback.format_exc()}'
                        )
                        message._close()
    except KeyboardInterrupt:
        print('Caught keyboard interrupt, exiting')
    finally:
        sel.close()


def process_action(message, services):
    """
    process the action from the client
    :param message: the message object
    :param services: the services object
    """
    if message.event == 'READ':
        action = message.request['action']
        if action == "register":
            message.response = services.register(message.request['type'], message.request['ip'], message.request['port'])
        elif action == "heartbeat":
            message.response = services.heartbeat(message.request['uuid'])
        elif action == "query":
            message.response = services.query(message.request['type'])
        else:
            message.response = "action not supported"
        message.set_selector_events_mask('w')



def accept_wrapper(sel, sock):
    """
    accept a connection
    """
    conn, addr = sock.accept()  # Should be ready to read
    print(f'Accepted connection from {addr}')
    conn.setblocking(False)
    message = ServerMessage(sel, conn, addr)
    sel.register(conn, selectors.EVENT_READ, data=message)

def send_request(content):

    sel = selectors.DefaultSelector()
    request = create_request(content)
    start_connection(sel, HOST, PORT, request)
    message=None
    try:
        while True:
            events = sel.select()
            for key, mask in events:
                message = key.data
                try:
                    message.process_events(mask)
                except Exception:
                    print(
                        f'Main: Error: Exception for {message.ipaddr}:\n'
                        f'{traceback.format_exc()}'
                    )
                    message.close()
            # Check for a socket being monitored to continue.
            if not sel.get_map():
                break
    except KeyboardInterrupt:
        print('Caught keyboard interrupt, exiting')
    finally:
        sel.close()
    if message is not None:
        return message

def create_request(action_item):
    return dict(
        type='text/json',
        encoding='utf-8',
        content=action_item,
    )

def start_connection(sel, host, port, request):
    addr = (host, port)
    print(f'Starting connection to {addr}')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.connect_ex(addr)
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    message = ClientMessage(sel, sock, addr, request)
    sel.register(sock, events, data=message)








if __name__ == '__main__':
    main()
