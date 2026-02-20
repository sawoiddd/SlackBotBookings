import json

class ConfigJsonReader:

    @staticmethod
    def GetTokens(path):
        with open(path, "r") as file:
            data = json.load(file)
            return data

#test
if __name__ == "__main__":
    print(ConfigJsonReader.GetTokens("config.json"))




