import re

def align_system_data(data_lines):
    max_length_0 = 0
    max_length_1 = 0
    for data_line in data_lines:
        elements = data_line.split(',')
        element1 = str(int((float(elements[1]))))

        max_length_0 = max(max_length_0, len(elements[0]))
        max_length_1 = max(max_length_1, len(element1))
    new_data_lines = []
    for i in range(len(data_lines)):
        elements = re.split(r'[\[\],]', data_lines[i])
        #------ Handle 0
        element0 = elements[0].ljust(max_length_0 + 3)
        #------ Handle 1
        element1 = str(int((float(elements[1]))))
        element1 = element1.ljust(max_length_1 + 3)
        #------ Handle 2
        element2 = elements[2].ljust(7)
        #------ Handle 4
        element4 = elements[4].ljust(15)
        #------ Handle 5
        element5 = elements[5]
        element5 = element5.lstrip()

        line = f"{element0}|{element1}|{element2}|{element4}|{element5}"

        new_data_lines.append(line)
    return new_data_lines


def align_lick_data(data_lines):
    max_length_0 = 0
    max_length_1 = 0
    max_length_5 = 0
    for data_line in data_lines:
        elements = data_line.split(',')
        print(elements)
        max_length_0 = max(max_length_0, len(elements[0]))
        max_length_1 = max(max_length_1, len(elements[1]))
        max_length_5 = max(max_length_1, len(elements[5]))
    new_data_lines = []
    for i in range(len(data_lines)):
        elements = data_lines[i].split(',')
        print(elements)
        #------ Handle 0
        element0 = elements[0].ljust(max_length_0 + 3)
        #------ Handle 1
        element1 = elements[1].ljust(max_length_1 + 3)
        #------ Handle 2
        element2 = elements[2]
        if i > 0: element2 = str(int(float(element2.lstrip())))
        element2 = element2.ljust(6)
        # ------ Handle 3
        element3 = elements[3]
        if i > 0: element3 = str(int(float(element3.lstrip())))
        element3 = element3.ljust(6)
        #------ Handle 4
        element4 = elements[4]
        if i > 0: element4 = str(int(float(element4.lstrip())))
        element4 = element4.ljust(6)
        #------ Handle 5
        element5 = elements[5].ljust(max_length_5 + 3)

        line = f"{element0}|{element1}|{element2}|{element3}|{element4}|{element5}"

        new_data_lines.append(line)
    return new_data_lines