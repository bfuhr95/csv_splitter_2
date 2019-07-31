    import math
    import tkinter as tk
    from tkinter.filedialog import askopenfilename
    from tkinter import StringVar
    from tkinter.filedialog import askdirectory
    import os
    ##Tkinter Style Settings

    LARGE_FONT  = ("Courier New", 12)

    root = tk.Tk

    class Program(tk.Tk):
        def __init__(self, *args, **kwargs):
            tk.Tk.__init__(self, *args, **kwargs)
            container = tk.Frame(self)
            container.pack(side = "top", fill = "both", expand = True)
            container.grid_rowconfigure(0, weight = 1)
            container.grid_columnconfigure(0, weight = 1)
            #tk.Frame.winfo_geometry('1000x1000')

            tk.Tk.wm_title(self, "CSV Splitter")
            tk.Tk.wm_geometry(self, "800x500")
            self.frames = {}

            frame = MainScreen(container, self)
            self.frames[MainScreen] = frame
            frame.grid(row = 0, column = 0, sticky = "nsew")

            self.show_frame(MainScreen)

        def show_frame(self, cont):
            frame = self.frames[cont]
            frame.tkraise()

    class MainScreen(tk.Frame):
        def __init__(self, parent, controller):
            tk.Frame.__init__(self, parent)
            self.filename = StringVar()
            self.return_value = StringVar()
            self.output_dir = StringVar()
            welcome_message = tk.Label(self, text = "Welcome to .csv Splitter v1.0", font = LARGE_FONT)
            welcome_message.grid(row = 0, column = 0, padx = 10, pady = 10)
            select_file_button = tk.Button(self, text = "Import File", font = LARGE_FONT, command = lambda: self.filename.set(askopenfilename()))
            select_file_button.grid(row = 1, column = 0, padx = 10, pady = 10)
            file_label = tk.Label(self, textvariable = self.filename, font = LARGE_FONT)
            file_label.grid(row = 1, column = 1)
            split_file_button = tk.Button(self, text = "Split File", font = LARGE_FONT, command = lambda: self.return_value.set(self.split_file(self.filesize.get())))
            split_file_button.grid(row = 4, column = 0, padx = 10, pady = 10)
            return_value = tk.Label(self, textvariable = self.return_value, font = LARGE_FONT)
            return_value.grid(row = 4, column = 2, sticky = "W")
            return_value_header = tk.Label(self, text = "Return Value:", font = LARGE_FONT)
            return_value_header.grid(row = 4, column = 1)
            self.filesize = tk.Entry(self)
            self.filesize.grid(row = 2, column = 1 )
            self.filesize_label = tk.Label(self, text = "Desired # of Lines per File:", font = LARGE_FONT)
            self.filesize_label.grid(row = 2, column = 0 )
            select_output_dir = tk.Button(self, text = "Output Directory", font = LARGE_FONT, command = lambda: self.output_dir.set(askdirectory()))
            select_output_dir.grid(row = 3, column = 0, padx = 10, pady = 10)
            file_label = tk.Label(self, textvariable = self.output_dir, font = LARGE_FONT)
            file_label.grid(row = 3, column = 1)
            #copyright = tk.Label(self, text = "Copyright Brandon Fuhr, 2019", font = LARGE_FONT)
            #copyright.grid(padx = 200, pady = 200)


        def split_file(self,split_cnt):
            os.chdir(self.output_dir.get())
            f = open(str(self.filename.get()), 'r')
            lines = f.readlines()
            f.close()
            i=0
            f = 0
            cnt = 0
            for file in range(0, int(math.ceil(float(len(lines))/float(split_cnt)))):
                filename = str('output') + str(f) + str('.csv')
                with open(filename, "w") as output:
                    print(filename)
                    for line in range(0,len(lines)):
                        i = i + 1
                        if i > float(split_cnt):
                            break
                        elif cnt == len(lines)-1:
                            return 0
                            break
                        else:
                            cnt = cnt + 1
                            output.write(lines[cnt])
                            print(f, i, cnt)
                            continue
                    f = f + 1
                    i = 0
                output.close()
    app = Program()
    app.mainloop()

