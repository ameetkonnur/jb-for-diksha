import base64
import os

with open('something.txt', 'r') as file:
    encoded_string = file.read()

decoded_bytes = base64.b64decode(encoded_string)

file_extension = "wav"
with open(f'decoded_file.{file_extension}', 'wb') as file:
    file.write(decoded_bytes)