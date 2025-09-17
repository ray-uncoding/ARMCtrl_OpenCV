# utils/arm_controller/pi_gpio_controller.py
import time
try:
    import RPi.GPIO as GPIO
    RPI_GPIO_AVAILABLE = True
except ImportError:
    print("[PiGPIOController] Warning: RPi.GPIO library not found. GPIO control will be simulated.")
    RPI_GPIO_AVAILABLE = False
except RuntimeError:
    print("[PiGPIOController] Error importing RPi.GPIO. This may mean you need to run as root or the library is not properly installed.")
    RPI_GPIO_AVAILABLE = False

class PiGPIOController:
    def __init__(self, relay_pins, led_pin=None, inverse_logic=True, gpio_mode=None, ready_pin=None):
        """
        Initialize the Raspberry Pi GPIO controller for arm relays.
        :param relay_pins: A list or tuple of 4 GPIO pin numbers (BCM mode) for relays 1-4.
        :param led_pin: GPIO pin number (BCM mode) for a test LED (optional).
        :param inverse_logic: True if relays are LOW active, False if HIGH active.
        :param gpio_mode: GPIO.BCM or GPIO.BOARD. Defaults to GPIO.BCM if RPi.GPIO is available.
        """
        self.relay_pins = relay_pins
        self.led_pin = led_pin
        self.inverse_logic = inverse_logic
        self.rpi_gpio_available = RPI_GPIO_AVAILABLE
        self.ready_pin = ready_pin
        self._ready_pin_state = 0  # 0=LOW, 1=HIGH

        if not self.rpi_gpio_available:
            print("[PiGPIOController] Operating in simulation mode. No actual GPIO changes will occur.")
            return

        if len(self.relay_pins) != 4:
            raise ValueError("relay_pins must be a list or tuple of 4 pin numbers.")

        if gpio_mode is None:
            self.gpio_mode = GPIO.BCM
        else:
            self.gpio_mode = gpio_mode
        
        GPIO.setmode(self.gpio_mode)
        GPIO.setwarnings(False) # Disable warnings for channels already in use

        for pin in self.relay_pins:
            GPIO.setup(pin, GPIO.OUT)
        
        if self.led_pin:
            GPIO.setup(self.led_pin, GPIO.OUT)

        if self.ready_pin is not None:
            GPIO.setup(self.ready_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        self.all_relays_off() # Initialize relays to off state

    def _set_relay_state(self, relay_index, state):
        """Sets a single relay's state, considering inverse_logic."""
        if not self.rpi_gpio_available:
            # print(f"[Simulate] Relay {relay_index+1} (Pin {self.relay_pins[relay_index]}) -> {'ON' if state else 'OFF'}")
            return

        pin = self.relay_pins[relay_index]
        # Determine the actual GPIO level based on state and inverse_logic
        # state=True means logical ON.
        # If inverse_logic is True, logical ON means GPIO.LOW.
        # If inverse_logic is False, logical ON means GPIO.HIGH.
        gpio_level_for_on = GPIO.LOW if self.inverse_logic else GPIO.HIGH
        gpio_level_for_off = GPIO.HIGH if self.inverse_logic else GPIO.LOW
        
        GPIO.output(pin, gpio_level_for_on if state else gpio_level_for_off)

    def _set_all_relays(self, r1_on, r2_on, r3_on, r4_on):
        """
        Sets the state of all four relays.
        Parameters are True for ON, False for OFF (logical state).
        """
        if not self.rpi_gpio_available:
            print(f"[Simulate] Relays -> R1:{'ON' if r1_on else 'OFF'}, R2:{'ON' if r2_on else 'OFF'}, R3:{'ON' if r3_on else 'OFF'}, R4:{'ON' if r4_on else 'OFF'}")
            return
            
        states = [r1_on, r2_on, r3_on, r4_on]
        for i in range(4):
            self._set_relay_state(i, states[i])
        # print(f"[PiGPIOController] Relays set: R1:{r1_on}, R2:{r2_on}, R3:{r3_on}, R4:{r4_on}")


    def all_relays_off(self):
        self._set_all_relays(False, False, False, False)
        # print("[PiGPIOController] All relays OFF.")

    def _execute_arm_sequence(self, r1, r2, r3, r4, action_name=""):
        print(f"[PiGPIOController] Executing {action_name} sequence...")
        # print("[PiGPIOController] Waiting for arm stabilization (3s)...")
        time.sleep(3)
        
        self._set_all_relays(r1, r2, r3, r4)
        print(f"[PiGPIOController] {action_name} - Relays activated.")
        # print("[PiGPIOController] Maintaining signal (3s)...")
        time.sleep(3)
        
        self.all_relays_off()
        print(f"[PiGPIOController] {action_name} - Relays deactivated. Sequence complete.")

    def _execute_arm_sequence_async(self, r1, r2, r3, r4, action_name=""):
        """
        Executes the arm sequence asynchronously to avoid blocking the main loop.
        """
        import threading

        def sequence():
            print(f"[PiGPIOController] Executing {action_name} sequence...")
            self._set_all_relays(r1, r2, r3, r4)
            print(f"[PiGPIOController] {action_name} - Relays activated.")
            time.sleep(3)  # Maintain signal
            self.all_relays_off()
            print(f"[PiGPIOController] {action_name} - Relays deactivated. Sequence complete.")

        threading.Thread(target=sequence).start()

    def _execute_arm_sequence_with_encoding(self, r1, r2, r3, r4, action_name=""):
        """
        Executes the arm sequence using R1 as the trigger and R2, R3, R4 as encoded signals.
        """
        import threading

        def sequence():
            print(f"[PiGPIOController] Executing {action_name} sequence with encoding...")
            self._set_relay_state(0, True)  # R1 high to indicate valid signal
            self._set_relay_state(1, r2)   # R2
            self._set_relay_state(2, r3)   # R3
            self._set_relay_state(3, r4)   # R4
            print(f"[PiGPIOController] {action_name} - Signal encoded: R1:{True}, R2:{r2}, R3:{r3}, R4:{r4}.")
            time.sleep(0.5)  # Maintain signal for 0.5 seconds
            self.all_relays_off()
            print(f"[PiGPIOController] {action_name} - Relays deactivated. Sequence complete.")

        threading.Thread(target=sequence).start()

    def _execute_arm_sequence_with_protocol(self, r2, r3, r4, action_name=""):
        """
        Executes the arm sequence with a protocol ensuring reliable signal transmission.
        """
        import threading

        def sequence():
            print(f"[PiGPIOController] Preparing {action_name} sequence...")
            self._set_relay_state(0, False)  # R1 low to indicate signal not ready
            self._set_relay_state(1, r2)     # R2
            self._set_relay_state(2, r3)     # R3
            self._set_relay_state(3, r4)     # R4
            print(f"[PiGPIOController] {action_name} - Signal encoded: R1:{False}, R2:{r2}, R3:{r3}, R4:{r4}.")
            time.sleep(1)  # Wait 1 second before activating R1

            self._set_relay_state(0, True)  # R1 high to indicate valid signal
            print(f"[PiGPIOController] {action_name} - Signal activated: R1:{True}, R2:{r2}, R3:{r3}, R4:{r4}.")
            time.sleep(7)  # Maintain signal for 7 seconds

            self.all_relays_off()  # Reset all relays to low
            print(f"[PiGPIOController] {action_name} - Relays deactivated. Sequence complete.")

        threading.Thread(target=sequence).start()

    def trigger_action_A(self): #紅色三角形
        self._execute_arm_sequence_with_protocol(False, False, True, "Action A (Encoded: 001)")

    def trigger_action_B(self): #紅色方形
        self._execute_arm_sequence_with_protocol(False, True, False, "Action B (Encoded: 010)")

    def trigger_action_C(self): #藍色三角形
        self._execute_arm_sequence_with_protocol(False, True, True, "Action C (Encoded: 011)")

    def trigger_action_D(self): #藍色方形
        self._execute_arm_sequence_with_protocol(True, False, False, "Action D (Encoded: 100)")

    def trigger_action_E(self): #綠色三角形
        self._execute_arm_sequence_with_protocol(True, False, True, "Action E (Encoded: 101)")

    def trigger_action_F(self): #綠色方形
        self._execute_arm_sequence_with_protocol(True, True, False, "Action F (Encoded: 110)")
        
    def run_test_led_sequence(self):
        if not self.rpi_gpio_available or not self.led_pin:
            print("[PiGPIOController] Test LED sequence skipped (GPIO not available or LED pin not set).")
            return

        print("[PiGPIOController] Test LED sequence started...")
        for _ in range(3):
            GPIO.output(self.led_pin, GPIO.HIGH)
            time.sleep(1)
            GPIO.output(self.led_pin, GPIO.LOW)
            time.sleep(1)
        print("[PiGPIOController] Test LED sequence finished.")

    def cleanup(self):
        if not self.rpi_gpio_available:
            print("[PiGPIOController] GPIO cleanup skipped (simulation mode).")
            return
        
        print("[PiGPIOController] Cleaning up GPIO resources...")
        self.all_relays_off() # Ensure all relays are off before cleaning up
        GPIO.cleanup()
        print("[PiGPIOController] GPIO cleanup complete.")

    def get_ready_pin(self):
        """取得 ready_pin 狀態，模擬時回傳 self._ready_pin_state"""
        if not self.rpi_gpio_available:
            return self._ready_pin_state
        if self.ready_pin is None:
            return 0
        return GPIO.input(self.ready_pin)

    def set_ready_pin_sim(self, value):
        """僅模擬用，設定 ready_pin 狀態"""
        self._ready_pin_state = 1 if value else 0

if __name__ == '__main__':
    # This is for basic testing of the PiGPIOController class itself.
    # You'll need to define your actual GPIO pins here and ensure RPi.GPIO is installed.
    
    if RPI_GPIO_AVAILABLE:
        print("Running PiGPIOController test...")
        # --- IMPORTANT: Define your Raspberry Pi GPIO pins here (BCM numbering) ---
        RELAY_PINS_FOR_TEST = [17, 27, 22, 23]  # Example: GPIO17, GPIO27, GPIO22, GPIO23
        LED_PIN_FOR_TEST = 18                   # Example: GPIO18
        INVERSE_RELAY_LOGIC = True              # Set to False if your relays are HIGH active
        # ---

        controller = None
        try:
            controller = PiGPIOController(
                relay_pins=[17, 27, 22, 23],
                led_pin=18,
                inverse_logic=True,
                gpio_mode=GPIO.BCM,
                ready_pin=26      # <--- 這裡指定
            )
            
            print("Testing LED sequence...")
            controller.run_test_led_sequence()
            time.sleep(2)
            
            print("Testing Action A...")
            controller.trigger_action_A()
            time.sleep(2) # Wait a bit before next action or cleanup
            
            # print("Testing Action B...")
            # controller.trigger_action_B()
            # time.sleep(2)
            
            # print("Testing Action C...")
            # controller.trigger_action_C()
            # time.sleep(2)
            
            # print("Testing Action D...")
            # controller.trigger_action_D()
            # time.sleep(2)

        except Exception as e:
            print(f"An error occurred during testing: {e}")
        finally:
            if controller:
                controller.cleanup()
    else:
        print("RPi.GPIO not available, running PiGPIOController simulation test.")
        # Test the class logic in simulation mode:
        sim_controller = PiGPIOController(relay_pins=[0,0,0,0], led_pin=0, inverse_logic=True) # Pins don't matter in sim
        sim_controller.trigger_action_A()
        sim_controller.run_test_led_sequence()
        sim_controller.cleanup()
