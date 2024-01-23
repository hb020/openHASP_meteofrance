#!/usr/bin/env python3
# Python 3

from cairosvg import svg2png
import requests

# for svg in svgs:
for i in range(1, 50):
    for postfix in ["j", "n", "bisj", "bisn"]:
        try:
            url = f"https://meteofrance.com/modules/custom/mf_tools_common_theme_public/svg/weather/p{i}{postfix}.svg"
            response = requests.get(url)
            if response.ok:
                print(f"p{i}{postfix}.svg") 
                with open(f"./img/mf_svg/p{i}{postfix}.svg", mode="wb") as file:
                    file.write(response.content)
                svg2png(url=url, write_to=f"./img/p{i}{postfix}.png", scale=1)
                svg2png(url=url, write_to=f"./img/p{i}{postfix}_big.png", scale=2)
        except Exception as e:
            print(f"Exception on p{i}{postfix}.svg: {str(e)}")
            pass

