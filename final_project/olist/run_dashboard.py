"""Start the local dashboard without rerunning the analysis pipeline."""
import argparse
from dashboard.app import app

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8050)
    args=parser.parse_args()
    app.run(host='127.0.0.1',port=args.port,debug=False)
