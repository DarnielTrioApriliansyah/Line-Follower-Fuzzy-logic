import cv2
import RPi.GPIO as GPIO
import time
import skfuzzy as fuzz
import numpy as np

# Setup GPIO pins for motor control
ENA = 18  # PWM pin for Motor A
ENB = 19  # PWM pin for Motor B
IN1 = 23  # Direction pin for Motor A
IN2 = 24  # Direction pin for Motor A
IN3 = 25  # Direction pin for Motor B
IN4 = 26  # Direction pin for Motor B

GPIO.setwarnings(False)  # Disable GPIO warnings
GPIO.setmode(GPIO.BCM)
GPIO.setup([ENA, ENB, IN1, IN2, IN3, IN4], GPIO.OUT)

# Initialize PWM for motors
left_pwm = GPIO.PWM(ENA, 100)  # 100 Hz frequency
right_pwm = GPIO.PWM(ENB, 100)  # 100 Hz frequency
left_pwm.start(0)
right_pwm.start(0)

def set_motor(left_speed, right_speed):
    # Convert speeds to integer
    left_speed = int(left_speed)
    right_speed = int(right_speed)

    # Clamp speeds to the range 0-255
    left_speed = max(0, min(255, left_speed))
    right_speed = max(0, min(255, right_speed))

    # Convert speed to duty cycle percentage
    left_duty_cycle = left_speed * 100 / 255
    right_duty_cycle = right_speed * 100 / 255

    # Set motor direction and duty cycle
    GPIO.output(IN1, left_speed > 0)
    GPIO.output(IN2, left_speed <= 0)
    left_pwm.ChangeDutyCycle(left_duty_cycle)

    GPIO.output(IN3, right_speed > 0)
    GPIO.output(IN4, right_speed <= 0)
    right_pwm.ChangeDutyCycle(right_duty_cycle)

def fuzzy_control(left_black_pixels, right_black_pixels, max_pixels):
    # Define fuzzy membership functions
    x_pixels = np.arange(0, max_pixels + 1, 1)
    x_speed = np.arange(0, 256, 1)  # Rentang kecepatan 0-255

    left_level_low = fuzz.trapmf(x_pixels, [0, 0, max_pixels*0.25, max_pixels*0.5])
    left_level_high = fuzz.trapmf(x_pixels, [max_pixels*0.25, max_pixels*0.5, max_pixels, max_pixels])

    right_level_low = fuzz.trapmf(x_pixels, [0, 0, max_pixels*0.25, max_pixels*0.5])
    right_level_high = fuzz.trapmf(x_pixels, [max_pixels*0.25, max_pixels*0.5, max_pixels, max_pixels])

    speed_slow = fuzz.trapmf(x_speed, [0, 0, 80, 120])
    speed_fast = fuzz.trapmf(x_speed, [80, 120, 255, 255])  # Pastikan maksimum 255

    # Fuzzification
    left_low = fuzz.interp_membership(x_pixels, left_level_low, left_black_pixels)
    left_high = fuzz.interp_membership(x_pixels, left_level_high, left_black_pixels)

    right_low = fuzz.interp_membership(x_pixels, right_level_low, right_black_pixels)
    right_high = fuzz.interp_membership(x_pixels, right_level_high, right_black_pixels)

    # Rule evaluation
    rule1 = np.fmin(left_low, speed_fast)
    rule2 = np.fmin(left_high, speed_slow)

    rule3 = np.fmin(right_low, speed_fast)
    rule4 = np.fmin(right_high, speed_slow)

    # Aggregation
    aggregated_left = np.fmax(rule1, rule2)
    aggregated_right = np.fmax(rule3, rule4)

    # Defuzzification
    left_speed = fuzz.defuzz(x_speed, aggregated_left, 'centroid')
    right_speed = fuzz.defuzz(x_speed, aggregated_right, 'centroid')

    return left_speed, right_speed

# Initialize webcam
cap = cv2.VideoCapture(0)  # Use the default camera

# Define video writer for recording
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec for AVI format
out = cv2.VideoWriter('output.avi', fourcc, 20.0, (frame_width, frame_height))

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Get frame dimensions
    height, width, _ = frame.shape

    # Define regions of interest (ROIs)
    box_width = 80
    box_height = 80
    left_box = frame[height//2 - box_height//2:height//2 + box_height//2, :box_width]
    right_box = frame[height//2 - box_height//2:height//2 + box_height//2, width-box_width:]

    # Convert ROIs to grayscale
    left_gray = cv2.cvtColor(left_box, cv2.COLOR_BGR2GRAY)
    right_gray = cv2.cvtColor(right_box, cv2.COLOR_BGR2GRAY)

    # Threshold the ROIs
    _, left_binary = cv2.threshold(left_gray, 110, 255, cv2.THRESH_BINARY_INV)
    _, right_binary = cv2.threshold(right_gray, 110, 255, cv2.THRESH_BINARY_INV)

    # Calculate pixel intensities
    left_black_pixels = cv2.countNonZero(left_binary)
    right_black_pixels = cv2.countNonZero(right_binary)

    # Apply fuzzy control
    max_pixels = box_width * box_height
    left_motor_speed, right_motor_speed = fuzzy_control(left_black_pixels, right_black_pixels, max_pixels)

    # Send commands to motors
    set_motor(left_motor_speed, right_motor_speed)

    # Draw rectangles around the ROIs
    cv2.rectangle(frame, (0, height//2 - box_height//2), (box_width, height//2 + box_height//2), (0, 255, 0), 2)
    cv2.rectangle(frame, (width-box_width, height//2 - box_height//2), (width, height//2 + box_height//2), (0, 255, 0), 2)

    # Display status on frame
    cv2.putText(frame, f"Left Speed: {int(left_motor_speed)}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
    cv2.putText(frame, f"Right Speed: {int(right_motor_speed)}", (width - 200, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    # Write the frame to the video file
    out.write(frame)

    # Show the frame
    cv2.imshow("Frame", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cap.release()
out.release()
cv2.destroyAllWindows()
GPIO.cleanup()
