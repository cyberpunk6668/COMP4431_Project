"""Controlled pet-page checks: actual local sprites, intercepted HTTP, zero LLM/IB."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
SID='11111111-1111-4111-8111-111111111111'
AID='22222222-2222-4222-8222-222222222222'


def check(browser,base,width,height):
    context=browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce')
    page=context.new_page();page.set_default_timeout(10000)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    calls=[];chats=[];case={'fail':False}
    connection={'epoch':'fixture-v15','seq':0,'generation':1,'session_id':SID,'language':'zh','engine':'deepseek','desktop_connected':False,'activities':[]}
    meta={'analysis_id':AID,'analysis_kind':'historical_options','source':'ibkr_historical','source_label':'Controlled historical fixture',
          'period':{'start':'2026-11-06','end':'2026-11-10'},'captured_at':'2026-11-11T01:00:00+00:00','historical_data':True,
          'notice':'历史样本，不代表当前情绪；完整交易时段覆盖未核验。','evidence_ids':['h.volume'],
          'evidence':[{'id':'h.volume','label':'样本成交变化','value':12029,'unit':'contracts','status':'incomparable','delta':None,'reason':'historical_bar_coverage_unverified'}]}
    session={'id':SID,'title':'Controlled shared conversation','messages':[],'active_analysis_id':AID,'active_analysis':deepcopy(meta),'analysis_history':[]}
    source={'id':'expert.put_call','title':'Put/call counts','url':'https://www.cboe.com/','publisher':'Cboe','snippet':'合约计数不是参与人数。'}
    def route(request):
        path=urlsplit(request.request.url).path;method=request.request.method
        calls.append((method,path))
        if path=='/pet':return request.fulfill(path=str(ROOT/'web/pet.html'),content_type='text/html')
        if path=='/api/models':data={'models':[{'id':'deepseek','label':'DeepSeek + RAG','available':True},{'id':'local','label':'Local fixture','available':True}]}
        elif path=='/api/companion/connection':
            if method=='PUT':
                body=request.request.post_data_json
                if body['session_id']!=connection['session_id']:connection['generation']+=1
                connection.update({key:value for key,value in body.items() if key in ('session_id','engine','language')})
            data=connection
        elif path=='/api/companion/events':
            assert 'surface=workspace' in request.request.url
            return request.fulfill(body='retry: 60000\n\nevent: reset\ndata: '+json.dumps({'epoch':'fixture-v15','seq':0,'generation':connection['generation'],'session_id':connection['session_id'],'type':'reset','payload':{'connection':connection}})+'\n\n',content_type='text/event-stream')
        elif path==f'/api/sessions/{SID}':data=session
        elif path=='/api/chat':
            body=request.request.post_data_json;chats.append(body)
            assert body['session_id']==SID and 'analysis_id' not in body
            if case['fail']:return request.fulfill(status=503,json={'detail':'controlled_failure'})
            first={'id':len(session['messages'])+1,'role':'user','content':body['message']}
            second={'id':len(session['messages'])+2,'role':'assistant','content':'<img src="bad" onerror="window.__unsafe=true"> 历史样本不能说明当前看空。 [h.volume] [expert.put_call]',
                    'mode':'offline','warning':'offline_requested','sources':[source],'analysis_context':deepcopy(meta)}
            session['messages'].extend([first,second]);data={'session_id':SID,'answer':second['content'],'mode':'offline','sources':[source],'analysis_context':meta}
        else:raise AssertionError('Unexpected API: '+path)
        return request.fulfill(json=data)
    page.route('**/api/**',route);page.route('**/pet',route)
    page.goto(base+'/pet');page.wait_for_function('window.finPilotPet && window.finPilotPet.getStatus().avatar?.renderer === "canvas2d"')
    assert not chats and not any(path=='/api/sessions' for _,path in calls)
    assert page.evaluate('window.finPilotPet.getStatus().native') is False
    page.locator('#pet-character').focus();page.keyboard.press('Enter');expect(page.locator('#pet-panel')).to_be_visible()
    expect(page.locator('#pet-analysis')).to_contain_text('2026-11-06')
    page.locator('#pet-input').fill('这批历史能说明多数人看空吗？');page.locator('#pet-send').click()
    expect(page.locator('#pet-messages > article')).to_have_count(2)
    assert len(chats)==1 and page.locator('#pet-messages img').count()==0
    assert page.evaluate('window.__unsafe === true') is False
    expect(page.locator('#pet-messages .message-mode')).to_have_text('本地响应')
    expect(page.locator('#pet-input')).to_have_value('')
    case['fail']=True;page.locator('#pet-input').fill('保留这个草稿');page.locator('#pet-send').click()
    expect(page.locator('#pet-error')).to_be_visible();expect(page.locator('#pet-input')).to_have_value('保留这个草稿')
    expect(page.locator('#pet-messages > article')).to_have_count(2)
    with page.expect_response(lambda r:'/api/companion/connection' in r.url and r.request.method=='PUT'):
        page.locator('#pet-engine').select_option('local')
    assert connection['engine']=='local'
    page.keyboard.press('Escape');expect(page.locator('#pet-panel')).to_be_hidden()
    page.locator('#pet-menu-toggle').click();expect(page.locator('#pet-menu')).to_be_visible()
    page.locator('#pet-size').select_option('250');assert page.evaluate('window.finPilotPet.getStatus().scale')==250
    page.keyboard.press('Escape');expect(page.locator('#pet-menu')).to_be_hidden()
    page.locator('#pet-character').focus();page.keyboard.press('Enter');page.locator('#pet-reduce').uncheck()
    page.wait_for_function('window.finPilotPet.getStatus().avatar?.reducedMotion === false')
    page.locator('#pet-reduce').check()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    placement_check='narrow_sheet_with_visible_close'
    if width>=1000:
        # Reproduce the native regression: move the pet near the left edge,
        # then open a panel which is wider than the available space on its left.
        page.keyboard.press('Escape')
        box=page.locator('#pet-character').bounding_box();assert box
        page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
        page.mouse.down();page.mouse.move(250+box['width']/2,box['y']+box['height']/2,steps=6);page.mouse.up()
        page.locator('#pet-character').focus();page.keyboard.press('Enter')
        expect(page.locator('#pet-panel')).to_have_attribute('data-placement','right')
        panel=page.locator('#pet-panel').bounding_box();pet=page.locator('#pet-character').bounding_box()
        assert panel and pet
        assert panel['x']>=pet['x']+pet['width']+15
        assert panel['x']+panel['width']<=width-11
        placement_check='left_pet_right_panel_no_overlap'
    else:
        expect(page.locator('#pet-panel')).to_have_attribute('data-placement','sheet')
    expect(page.locator('#pet-close-panel')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
    assert not errors,errors
    shot=ROOT/f'reports/screenshots/pet-v15/pet-{width}.png';shot.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(shot),animations='disabled')
    result={'width':width,'height':height,'status':'passed','checks':15,'fixture_chat_posts':len(chats),'external_model_calls':0,'broker_requests':0,'panel_placement_check':placement_check,'avatar':page.evaluate('window.finPilotPet.getStatus().avatar'),'page_errors':errors,'screenshot':shot.relative_to(ROOT).as_posix()}
    context.close();return result


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8000');args=parser.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        results=[check(browser,args.base,w,h) for w,h in [(320,740),(390,844),(1440,1000)]]
        browser.close()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed','scope':'Controlled API fixtures with actual local sprite renderer; not native Windows or real provider validation.','viewports':results,'checks_per_viewport':15,'new_broker_requests':0,'external_model_calls':0,
            'checks':['actual_canvas2d_renderer','browser_surface_not_native_presence','no_session_list_scan','no_automatic_chat','keyboard_panel_open','historical_period_visible','shared_chat_omits_analysis_id','authoritative_messages_no_duplicate','html_not_executed','actual_response_mode_label','failed_request_retains_draft','model_preference_update','menu_size_and_escape','reduce_motion_and_no_horizontal_overflow','available_side_panel_placement_or_narrow_sheet_with_close']}
    (ROOT/'reports/pet_browser_v15.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'viewports':len(results),'checks_per_viewport':15}))


if __name__=='__main__':main()
