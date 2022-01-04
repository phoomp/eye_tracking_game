# import queue
# import threading
import pygame
# from win32api import GetSystemMetrics
import random
# import threading
# from queue import Empty, Queue
import collections
import time
from pygame.image import save
# from msvcrt import getch, kbhit
# from pynput.mouse import Button, Controller
# from pynput import mouse
# import time
# import glob
# import natsort
import zmq
# from msgpack import unpackb, packb, loads
from msgpack import loads

import numpy as np
from scipy.interpolate import splprep, splev


# Adjustable Parameters
blink_confidence = 0.7

# Flags

# Enable recording in Pupil Capture.
enable_pupil_capture_recording = False

# Dependent on enable_recording
reset_timestamp_at_record_start = False
save_system_time = True # START and END only

flags_list = [enable_pupil_capture_recording, reset_timestamp_at_record_start, save_system_time]

# Pupil Capture port
req_port = "50021"


class Unit_delay(): 
    def __init__(self):
        self.last = pygame.time.get_ticks()
        self.cooldown = 3000
        self.interrupt = False

    def fire(self):
        self.now = pygame.time.get_ticks()
        # print(now, self.last)
        if self.now - self.last >= self.cooldown:
            self.last = self.now
            self.interrupt = False
        else:
            self.interrupt = True

    def trig(self):
        return self.interrupt


class Pupil_tracking(pygame.sprite.Sprite):
    def __init__(self, width, height):
        super().__init__()

        self.width = width
        self.height = height
        self.x = 0
        self.y = 0
        self.conf = 0
        self.smooth_x, self.smooth_y = 1.3, 1.3 #1.3, 1.3 works best 

        self.list_x = collections.deque(maxlen=15)
        self.list_y = collections.deque(maxlen=15)

        context = zmq.Context()
        addr = "127.0.0.1"
        req = context.socket(zmq.REQ)
        req.connect("tcp://{}:{}".format(addr, req_port))
        req.send_string("SUB_PORT")
        sub_port = req.recv_string()
        self.q_gaze_pos = collections.deque(maxlen=15)
        self.q_gaze_conf = collections.deque(maxlen=15)
        self.sub = context.socket(zmq.SUB)
        self.sub.connect("tcp://{}:{}".format(addr, sub_port))
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "surface")

    def update(self):
        try:
            self.topic = self.sub.recv_string(flags=zmq.NOBLOCK)
            self.msg = self.sub.recv()  # bytes
            self.surfaces = loads(self.msg, raw=False)
            self.surf = self.surfaces["gaze_on_surfaces"]

            self.raw_x = sum([i['norm_pos'][0] for i in self.surf]) / len(self.surf)
            self.raw_y = sum([i['norm_pos'][1] for i in self.surf]) / len(self.surf)

            # Smoothing

            self.smooth_x += 0.12 * (self.raw_x - self.smooth_x)
            self.smooth_y += 0.12 * (self.raw_y - self.smooth_y)
            
            self.x = self.smooth_x
            self.y = self.smooth_y

            # Uncommnet for raw tracking

            # self.x = self.raw_x
            # self.y = self.raw_y

            # Inverse y-value for correct tracking

            self.y = 1 - self.y

            self.x *= int(self.width)
            self.y *= int(self.height)

            self.conf = sum([i['confidence'] for i in self.surf]) / len(self.surf)

        except zmq.Again as e:
            self.gaze_pos = "no msg"
            # self.q.append(self.surf)

    def receive_gaze_info(self):
        return self.x, self.y, self.conf

    def point(self):
        return self.gaze_pos, self.q_gaze_pos, self.q_gaze_conf


class Pupil_visual(pygame.sprite.Sprite):
    def __init__(self, width, height):
        super().__init__()
        self.rec_wh = 120
        self.width = width
        self.height = height
        self.image = pygame.Surface([self.rec_wh, self.rec_wh],
                                    pygame.SRCALPHA)

        pygame.draw.circle(self.image, (255, 0, 0, 127),
                           (int(self.rec_wh / 2), int(self.rec_wh / 2)),
                           self.rec_wh / 2)
        self.rect = self.image.get_rect()

        # Top left corner reduces marker accuracy, center is better.
        self.pos_x = (self.width / 2) - (self.rec_wh / 2)
        self.pos_y = (self.height / 2) - (self.rec_wh / 2)

    def update(self, x, y):
        self.pos_x = x - (self.rec_wh / 2)
        self.pos_y = y - (self.rec_wh / 2)

    def draw(self, screen):
        screen.blit(self.image, [self.pos_x, self.pos_y])


# Markers
# W, H, M, C (i loop)


class Static_marker(pygame.sprite.Sprite):
    def __init__(self, width, height, marker, count):
        super().__init__()
        self.count = count
        self.tag_pos = [(0, 0), (width - marker, 0), (0, height - marker),
                        (width - marker, height - marker)]
        # self.tag_dir = ['D:/RF_eye_project/remote_pupil/tag_imgs/tag.png',
        #                 'D:/RF_eye_project/remote_pupil/tag_imgs/tag1.png',
        #                 'D:/RF_eye_project/remote_pupil/tag_imgs/tag2.png',
        #                 'D:/RF_eye_project/remote_pupil/tag_imgs/tag3.png']

        self.tag_dir = ['tag.png', 'tag1.png', 'tag2.png', 'tag3.png']

        self.image = pygame.image.load(self.tag_dir[self.count])
        self.image.convert()
        self.rect = self.image.get_rect()
        self.rect.x = self.tag_pos[self.count][0]
        self.rect.y = self.tag_pos[self.count][1]


class Static_line(pygame.sprite.Sprite):
    def __init__(self, width, height, marker):
        super().__init__()
        # self.surf_size = [[width, 10], [10, height]]
        self.image = pygame.Surface([width, height], pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.rect.x = 0
        self.rect.y = 0
        pygame.draw.rect(self.image, (0, 0, 255), (0, 0, width, height), 10)

class Text(pygame.sprite.Sprite):
    def __init__(self, width, height, marker):
        super().__init__()
        self.font = pygame.font.SysFont("Arial", 32)
        self.marker = marker

    def update(self, score):
        self.textSurf = self.font.render("SCORE : " + str(score), 1, (0, 0, 0))

    def draw(self, screen):
        screen.blit(self.textSurf, [self.marker, self.marker / 6])

class Timer(pygame.sprite.Sprite):
    def __init__(self, width, height, marker):
        super().__init__()
        self.width = width
        self.height = height
        self.marker = marker
        self.font = pygame.font.SysFont("Arial", 32)

        self.margin = 50

    def update(self, time_remaining):
        self.textSurf = self.font.render("Timer: " + str(time_remaining), 1, (0, 0, 0))
        
    def draw(self, screen):
        self.text_rect = self.textSurf.get_rect(center=(self.width / 2, self.height / 2))
        screen.blit(self.textSurf, [self.marker, (self.marker / 6) + self.margin])

# green circle for target
class Gaze_point(pygame.sprite.Sprite):
    def __init__(self, width, height, visible):
        super().__init__()
        self.rec_wh = 40
        self.width = width
        self.height = height
        self.visible = visible

        self.image = pygame.Surface([self.rec_wh, self.rec_wh], pygame.SRCALPHA)
        pygame.draw.circle(self.image, (0, 255, 0),
                           (int(self.rec_wh / 2), int(self.rec_wh / 2)), 20)
        self.rect = self.image.get_rect()
        self.update_graphic = True

    def update(self):
        self.color = (0, 255, 0)
        
        if not self.visible:
            self.color = (255, 255, 255, 0)

        pygame.draw.circle(self.image, self.color,
                           (int(self.rec_wh / 2), int(self.rec_wh / 2)), 20)
        
        self.rect = self.image.get_rect()

        margin = 50
        self.rect.x = random.randrange(self.width - (margin * 2)) + margin / 2
        self.rect.y = random.randrange(self.height - (margin * 2)) + margin / 2

class Summary_Screen(object):
    def __init__(self, width, height, unintended, intended, start_time, end_time, screen):
        self.width = width
        self.height = height
        self.unintended = unintended
        self.intended = intended
        self.start_time = start_time
        self.end_time = end_time
        self.screen = screen

        self.g_over_text = Game_Over_Text(self.width, self.height)
        self.blink_summary_text = Blink_Result(self.width, self.height, self.unintended, self.intended)
        self.system_time_result = System_Time_Result(self.width, self.height, self.start_time, self.end_time)

        self.screen.fill((255, 255, 255))

        self.g_over_text.draw(self.screen)
        self.blink_summary_text.draw(self.screen)
        self.system_time_result.draw(self.screen)

        pygame.display.update()


class Game_Over_Text(pygame.sprite.Sprite):
    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.margin = 150

        self.font = pygame.font.SysFont('Arial', 64)
        self.surf = self.font.render('Game Over!', 1, (0, 0, 0))

    def draw(self, screen):
        text_rect = self.surf.get_rect(center=(self.width / 2, self.margin))
        screen.blit(self.surf, text_rect)


class Blink_Result(pygame.sprite.Sprite):
    def __init__(self, width, height, unintended, intended):
        super().__init__()
        self.width = width
        self.height = height
        self.unintended = unintended
        self.intended = intended

        self.margin = 150

        self.font = pygame.font.SysFont('Arial', 32)

        self.total = self.unintended + self.intended

        print(self.unintended + self.intended)

        txt_to_display = f'Unintentional Blinks: {self.unintended} ({self.unintended / self.total * 100}%)    Intentional Blinks: {self.intended} ({self.intended / self.total * 100}%)    Total: {self.unintended + self.intended}'

        self.surf = self.font.render(txt_to_display, 1, (0, 0, 0))

    def draw(self, screen):
        text_rect = self.surf.get_rect(center=(self.width / 2, self.height / 2))
        screen.blit(self.surf, text_rect)

class System_Time_Result(pygame.sprite.Sprite):
    def __init__(self, width, height, start_time, end_time):
        super().__init__()
        self.width = width
        self.height = height
        self.start_time = start_time
        self.end_time = end_time
        self.margin = 100

        self.font = pygame.font.SysFont('Arial', 24)
        self.surf = self.font.render(f'System Time: {self.start_time} - {self.end_time}', 1, (0, 0, 0))

    def draw(self, screen):
        text_rect = self.surf.get_rect(center=(self.width / 2, self.height - self.margin))
        screen.blit(self.surf, text_rect)


class Game(object):
    def __init__(self, width, height, marker, unintended_blinks, intended_blinks):
        count = 0
        self.score = 0

        self.time = 20 # time in seconds
        self.time_remaining = self.time

        # Predefined values

        self.game_over = False
        self.all_sprite = pygame.sprite.Group()
        self.width = width
        self.height = height
        self.marker = marker
        self.check_state = False

        # Game Data
        self.unintended_blinks = unintended_blinks
        self.intended_blinks = intended_blinks
        self.lastblink = pygame.time.get_ticks()
        self.delay = Unit_delay()
        self.wait = False
        self.last_blink = False
        self.last_x = -1
        self.last_y = -1

        self.system_start_time = None
        self.system_end_time = None

        # Load corner markers

        for i in range(4):
            self.static = Static_marker(self.width, self.height, self.marker,
                                        i)
            self.all_sprite.add(self.static)

        # static line class
        self.line = Static_line(self.width, self.height, self.marker)

        self.gaze = Gaze_point(self.width, self.height, True)
        self.text = Text(self.width, self.height, self.marker)
        self.timer = Timer(self.width, self.height, self.marker)
        self.pupil = Pupil_tracking(self.width, self.height)
        self.pupil_visual = Pupil_visual(self.width, self.height)
        self.x, self.y, self.conf = self.pupil.receive_gaze_info()

        self.text.update(self.score)
        self.timer.update(self.time_remaining)
        self.pupil.update()

        self.all_sprite.add(self.line)
        self.all_sprite.add(self.gaze)
        # self.all_sprite.add(self.text)
        self.all_sprite.update()

        communication_required = False

        for flag in flags_list:
            if flag:
                communication_required = True
                break

        if communication_required:
            ctx = zmq.Context()
            pupil_remote = zmq.Socket(ctx, zmq.REQ)
            pupil_remote.connect('tcp://127.0.0.1:' + req_port)
        
            if enable_pupil_capture_recording:
                pupil_remote.send_string('R')
                print(pupil_remote.recv_string())

            if reset_timestamp_at_record_start:
                pupil_remote.send_string('T 0000.00')
                print(pupil_remote.recv_string())
            
        if save_system_time:
            self.system_start_time = time.time()

        self.start_ticks = pygame.time.get_ticks()

    def process_event(self, screen):
        if self.game_over:
                return True
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
        return False

    def logic_update(self):
        if not self.game_over:
            self.pupil.update()
            self.now = pygame.time.get_ticks()
            time_remaining = int(self.time - (self.now - self.start_ticks) / 1000)
            if time_remaining <= 0:
                self.game_over = True
                if enable_pupil_capture_recording:
                    ctx = zmq.Context()
                    pupil_remote = zmq.Socket(ctx, zmq.REQ)
                    pupil_remote.connect('tcp://127.0.0.1:' + req_port)
                    pupil_remote.send_string('r')
                    print(pupil_remote.recv_string())

                if save_system_time:
                    self.system_end_time = time.time()

            else:
                self.timer.update(time_remaining)

            # Get pupil info
            self.x, self.y, self.conf = self.pupil.receive_gaze_info()
            self.surf = [self.x, self.y]

            # Threshold
            threshold = 240

            # Confidence / Blinking
            blinked = False

            print(self.conf)

            if self.conf < blink_confidence and not self.last_blink:
                blinked = True
                self.last_blink = blinked
                # print(self.conf)
    
            if self.conf >= blink_confidence:
                self.last_blink = False

            # Update pupil visualizer location
            accuracy_confidence = 0.8
            if self.conf >= accuracy_confidence:
                self.pupil_visual.update(self.x, self.y)
                self.last_x = self.x
                self.last_y = self.y

            close_to_target = (abs(self.gaze.rect.x - self.last_x) <= threshold) \
                               and (abs(self.gaze.rect.y - self.last_y) <= threshold)

            # if blinked:
                # print(self.last_x)

            # Blink counting
            if blinked and close_to_target:
                self.intended_blinks += 1
                print('change green circle')
            elif blinked and not close_to_target:
                self.unintended_blinks += 1

            # Logic when blinked
            if (blinked and close_to_target) or self.delay.interrupt:

                if not self.delay.interrupt:
                    self.score += 1
                    self.text.update(self.score)
                    # Make green circle invisible
                    self.gaze.visible = False
                    self.delay = Unit_delay()
                    self.delay.interrupt = True

                else:
                    self.delay.fire()
                    if not self.delay.trig():
                        self.gaze.visible = True 
                        self.gaze.update()
                    else:
                        self.gaze.update()           

    def display_frame(self, screen):
        screen.fill((255, 255, 255))

        self.all_sprite.draw(screen)
        self.text.draw(screen)
        self.timer.draw(screen)
        self.pupil_visual.draw(screen)

        # print(self.pupil.point())
        pygame.display.update() 

class Reading_Test(object):
    def __init__(self, width, height, marker):
        count = 0
        self.score = 0

        # Predefined values

        self.game_over = False
        self.all_sprite = pygame.sprite.Group()
        self.width = width
        self.height = height
        self.marker = marker


        # Game Data

        self.system_start_time = None
        self.system_end_time = None

        # Load corner markers

        for i in range(4):
            self.static = Static_marker(self.width, self.height, self.marker,
                                        i)
            self.all_sprite.add(self.static)

        # static line class
        self.line = Static_line(self.width, self.height, self.marker)
        self.next_button = Next_Button(self.width, self.height, None)
        self.next_desc = Next_Button_Desc('Next', self.width, self.height, None)

        self.text = MultiLine_Text(self.width, self.height)

        self.all_sprite.add(self.line)
        self.all_sprite.add(self.next_button)
        self.all_sprite.update()

        communication_required = False

        for flag in flags_list:
            if flag:
                communication_required = True
                break

        if communication_required:
            ctx = zmq.Context()
            pupil_remote = zmq.Socket(ctx, zmq.REQ)
            pupil_remote.connect('tcp://127.0.0.1:' + req_port)
        
            if enable_pupil_capture_recording:
                pupil_remote.send_string('R')
                print(pupil_remote.recv_string())

            if reset_timestamp_at_record_start:
                pupil_remote.send_string('T 0000.00')
                print(pupil_remote.recv_string())
            
        if save_system_time:
            self.system_start_time = time.time()

        self.start_ticks = pygame.time.get_ticks()

    def process_event(self, screen):
        if self.game_over:
                return True
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True 
            
            n_button = self.next_button.click(event)
            
            if n_button:
                if enable_pupil_capture_recording:
                    ctx = zmq.Context()
                    pupil_remote = zmq.Socket(ctx, zmq.REQ)
                    pupil_remote.connect('tcp://127.0.0.1:' + req_port)
                    pupil_remote.send_string('r')
                    print(pupil_remote.recv_string())
                pygame.quit()
                main()

        return False

    def logic_update(self):
        pass           

    def display_frame(self, screen):
        screen.fill((255, 255, 255))

        self.all_sprite.draw(screen)
        self.next_desc.draw(screen)
        self.text.blit_text(screen)

        # print(self.pupil.point())
        pygame.display.update() 

class MultiLine_Text(pygame.sprite.Sprite):
    def __init__(self, width, height):
        super().__init__()

        self.width = width 
        self.height = height

        self.text = '''
            Alice was beginning to get very tired of sitting by her sister on the bank, and of having nothing to do once or twice she had peeped into the book her sister was reading, but it had no pictures or conversations in it, and what is the use of a book,' thought Alice without pictures or conversation?' So she was considering in her own mind as well as she could, for the hot day made her feel very sleepy and stupid , whether the pleasure of making a daisy chain would be worth the trouble of getting up and picking the daisies, when suddenly a White Rabbit with pink eyes ran close by her.
            There was nothing so VERY remarkable in that nor did Alice think it so VERY much out of the way to hear the Rabbit say to itself, Oh dear! Oh dear! I shall be late!' when she thought it over afterwards, it occurred to her that she ought to have wondered at this, but at the time it all seemed quite natural but when the Rabbit actually TOOK A WATCH OUT OF ITS WAISTCOAT POCKET, and looked at it, and then hurried on, Alice started to her feet, for it flashed across her mind that she had never before seen a rabbit with either a waistcoat pocket, or a watch to take out of it, and burning with curiosity, she ran across the field after it, and fortunately was just in time to see it pop down a large rabbit hole under the hedge.
        '''
        self.font = pygame.font.SysFont('Arial', 32)
        self.pos = (350, 350)
        self.color = pygame.Color('black')
        
    # Call from display_frame
    def blit_text(self, screen):
        words = [word.split(' ') for word in self.text.splitlines()] 
        space = self.font.size(' ')[0]  
        max_width, max_height = screen.get_size()
        max_width -= 300
        x, y = self.pos
        for line in words:
            for word in line:
                word_surface = self.font.render(word, 0, self.color)
                word_width, word_height = word_surface.get_size()
                if x + word_width >= max_width:
                    x = self.pos[0]  
                    y += word_height + 10  
                screen.blit(word_surface, (x, y))
                x += word_width + space
            x = self.pos[0]
            y += word_height + 10

class Next_Button(pygame.sprite.Sprite):
    def __init__(self, width, height, delta):
        super().__init__()
        self.width = width
        self.height = height
        self.delta = delta

        b_width = 200
        b_height = 100

        self.image = pygame.Surface([b_width, b_height], pygame.SRCALPHA)
        pygame.draw.rect(self.image, (0, 0, 120, 220), (0, 0, b_width, b_height))
        self.rect = self.image.get_rect(center=(self.width / 2, (self.height - 80)))  

    def click(self, event):
        x, y = pygame.mouse.get_pos()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if pygame.mouse.get_pressed()[0]:
                if self.rect.collidepoint(x, y):
                    return True
        return False 

class Next_Button_Desc(pygame.sprite.Sprite):
    def __init__(self, desc, width, height, delta):
        super().__init__()
        self.desc = desc
        self.width = width
        self.height = height

        self.font = pygame.font.SysFont('Arial', 24)
        self.textSurf = self.font.render(self.desc, 1, (255, 255, 255))

    def draw(self, screen):
        text_rect = self.textSurf.get_rect(center=(self.width / 2, (self.height - 80)))
        screen.blit(self.textSurf, text_rect)

class Button(pygame.sprite.Sprite):
    def __init__(self, width, height, delta):
        super().__init__()
        self.width = width
        self.height = height
        self.delta = delta

        b_width = 450
        b_height = 150

        self.image = pygame.Surface([b_width, b_height], pygame.SRCALPHA)
        pygame.draw.rect(self.image, (0, 0, 120, 220), (0, 0, b_width, b_height))
        self.rect = self.image.get_rect(center=(self.width / 2, (self.height / 2) + self.delta))

    def click(self, event):
        x, y = pygame.mouse.get_pos()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if pygame.mouse.get_pressed()[0]:
                if self.rect.collidepoint(x, y):
                    print('Button Pressed!') 
                    return True

        return False

class Button_Desc(pygame.sprite.Sprite):
    def __init__(self, desc, width, height, delta):
        super().__init__()
        self.desc = desc
        self.width = width
        self.height = height
        self.delta = delta

        self.font = pygame.font.SysFont('Arial', 32)
        self.textSurf = self.font.render(self.desc, 1, (255, 255, 255))

    def draw(self, screen):
        text_rect = self.textSurf.get_rect(center=(self.width / 2, (self.height / 2) + self.delta))
        screen.blit(self.textSurf, text_rect)

class Title(pygame.sprite.Sprite):
    def __init__(self, width, top_margin):
        super().__init__()
        self.width = width
        self.margin = top_margin

        self.font = pygame.font.SysFont('Arial', 64)
        self.surf = self.font.render('Data Collection Game', 1, (0, 0, 0))

    def draw(self, screen):
        text_rect = self.surf.get_rect(center=(self.width / 2, self.margin))
        screen.blit(self.surf, text_rect)

class Quit_Button(pygame.sprite.Sprite):
    def __init__(self, width, height, margin):
        super().__init__()
        self.width = width
        self.height = height
        self.margin = margin

        b_width = 100
        b_height = 50

        self.image = pygame.Surface([b_width, b_height], pygame.SRCALPHA)
        pygame.draw.rect(self.image, (0, 0, 120, 220), (0, 0, b_width, b_height))
        self.rect = self.image.get_rect(center=(self.width / 2, self.height - self.margin))

    def click(self, event):
        x, y = pygame.mouse.get_pos()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if pygame.mouse.get_pressed()[0]:
                if self.rect.collidepoint(x, y):
                    print('Button Pressed!') 
                    return True

        return False

class Quit_Button_Desc(pygame.sprite.Sprite):
    def __init__(self, width, height, bottom_margin):
        super().__init__()
        self.width = width
        self.height = height
        self.margin = bottom_margin

        self.font = pygame.font.SysFont('Arial', 16)
        self.surf = self.font.render('Quit', 1, (255, 255, 255))

    def draw(self, screen):
        text_rect = self.surf.get_rect(center=(self.width / 2, self.height - self.margin))
        screen.blit(self.surf, text_rect)

    def click(self, event):
        x, y = pygame.mouse.get_pos()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if pygame.mouse.get_pressed()[0]:
                if self.rect.collidepoint(x, y):
                    pygame.quit()

class Game_Selector(object):
    def __init__(self, screen_width, screen_height, marker_size, screen, clock):
        
        self.game = None

        top_margin = 100
        bottom_margin = 30

        self.b_width = 300
        self.b_height = 150

        self.width = screen_width
        self.height = screen_height
        self.marker = marker_size
        self.screen = screen
        self.clock = clock

        self.unintended_blinks = 0
        self.intended_blinks = 0

        # Add more buttons
        button1_delta = -200
        self.button1 = Button(self.width, self.height, button1_delta)
        self.desc1 = Button_Desc('Fixed Eye Position', self.width, self.height, button1_delta)

        button2_delta = 0
        self.button2 = Button(self.width, self.height, button2_delta)
        self.desc2 = Button_Desc('Free Head Movement', self.width, self.height, button2_delta)

        button3_delta = 200
        self.button3 = Button(self.width, self.height, button3_delta)
        self.desc3 = Button_Desc('Fixed Head Reading', self.width, self.height, button3_delta)

        self.title = Title(self.width, top_margin)

        self.quit_button = Quit_Button(self.width, self.height, bottom_margin)
        self.quit_button_desc = Quit_Button_Desc(self.width, self.height, bottom_margin)

        self.screen.fill((255, 255, 255))

        self.all_sprites = pygame.sprite.Group()
        self.all_sprites.add(self.button1)
        self.all_sprites.add(self.button2)
        self.all_sprites.add(self.button3)

        self.all_sprites.add(self.quit_button)
        self.all_sprites.draw(self.screen)

        self.desc1.draw(self.screen)
        self.desc2.draw(self.screen)
        self.desc3.draw(self.screen)

        self.title.draw(self.screen)
        self.quit_button_desc.draw(self.screen)
        pygame.display.update()
    
    def process_event(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True

            button1 = self.button1.click(event)
            button2 = self.button2.click(event)
            button3 = self.button3.click(event)
            
            if button1:
                self.game = Game(self.width, self.height, self.marker, self.unintended_blinks, self.intended_blinks)
                self.call_game(self.game)

            if button2:
                self.game = Game(self.width, self.height, self.marker, self.unintended_blinks, self.intended_blinks)
                self.call_game(self.game) 

            if button3:
                self.game = Reading_Test(self.width, self.height, self.marker)
                self.call_game(self.game)

            quit_button_pressed = self.quit_button.click(event)
            
            if quit_button_pressed:
                pygame.quit()
                quit()

    def call_game(self, game):
        done = False
        while not done:
            done = game.process_event(self.screen)
            game.logic_update()
            game.display_frame(self.screen)
            self.clock.tick(360)
            
        self.call_game_summary(Summary_Screen(self.width, self.height, self.game.unintended_blinks, self.game.intended_blinks, self.game.system_start_time, self.game.system_end_time, self.screen))

    def call_game_summary(self, summary): 
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pygame.quit()
                    main()

def main():

    pygame.init()
    pygame.font.init()
    display_width = 2304
    display_height = 1296
    marker_size = 300
    screen = pygame.display.set_mode((display_width, display_height))

    done = False
    clock = pygame.time.Clock()

    game = Game_Selector(display_width, display_height, marker_size, screen, clock)

    while not done:

        done = game.process_event()
        # game.logic_update()
        # game.display_frame(screen)
        # print(clock.get_fps())
        clock.tick(360)

    pygame.quit()


def game_main():

    pygame.init()
    pygame.font.init()
    display_width = 2304
    display_height = 1296
    marker_size = 300
    screen = pygame.display.set_mode((display_width, display_height))

    done = False
    clock = pygame.time.Clock()

    game = Game(display_width, display_height, marker_size)

    while not done:

        done = game.process_event()
        game.logic_update()
        game.display_frame(screen)
        clock.tick(360)

    pygame.quit()


if __name__ == "__main__":
    main()
