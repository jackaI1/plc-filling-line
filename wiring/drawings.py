"""Shared vector drawing primitives create native DXF and printable PDF sheets."""
from collections import defaultdict
from pathlib import Path

MM = 72 / 25.4
WIDTH, HEIGHT = 420, 297


class Sheet:
    def __init__(self, title):
        self.title = title
        self.shapes = []

    def line(self, x1, y1, x2, y2):
        self.shapes.append(('line', (x1, y1, x2, y2)))

    def rect(self, x, y, w, h):
        self.shapes.append(('rect', (x, y, w, h)))

    def text(self, x, y, text, size=2.8):
        self.shapes.append(('text', (x, y, str(text), size)))

    def frame(self, number):
        self.rect(10, 10, 400, 277)
        self.line(10, 27, 410, 27)
        self.text(16, 277, self.title, 5)
        self.text(16, 20, 'PLC FILLING LINE | Jack Lai | revision A | simulated 24 V DC panel', 3)
        self.text(16, 14, 'Study drawing only. No mains design, protective coordination or hardware safety circuit.', 2.5)
        self.text(389, 18, f'{number:02}', 4)


def endpoint(wire, side):
    return f"{wire[side+'_device']}:{wire[side+'_pin']}"


def sheets_for(panel):
    from .project import bom, terminal_schedule
    sheets = []
    mapped = [p for p in panel['pins'] if p.get('address')]
    power = Sheet('01 / POWER DISTRIBUTION')
    power.text(18, 262, 'Supply: external regulated 24 V DC. ' + ('Nominal 1 A fused control branch.' if mapped else 'Three independent switch-and-lamp circuits.'), 3)
    power.text(18, 254, 'Blue = signal; red = +24 V; black = 0 V. 18 AWG simulated cuts; no current-rating claim.', 3)
    supply = [w for w in panel['wires'] if w['sheet'] == 'Power']
    if not supply:
        power.text(18, 230, 'Cockpit example: J1 pins 1-3 receive external switched +24 V; pins 4-6 return to 0 V.', 3)
        power.text(18, 215, 'Three toggle switches drive three 24 V indicators through one six-pin connector.', 3)
    for n, w in enumerate(supply):
        y = 230 - 27 * n
        power.rect(22, y-7, 65, 14)
        power.rect(300, y-7, 85, 14)
        power.text(26, y-1, endpoint(w, 'from'), 4)
        power.text(304, y-1, endpoint(w, 'to'), 4)
        power.line(87, y, 300, y)
        power.text(116, y+3, f"W{w['wire']} / {w['gauge']} / {w['colour']} / {w['length_m']} m", 3)
    if mapped:
        power.text(18, 93, 'D24 and D0 are internally common distribution blocks; each numbered port takes one wire.', 3)
        power.text(18, 84, 'X1-X15 are two-sided feedthrough terminals: F (field) is internally connected to P (PLC).', 3)
        power.text(18, 75, 'K1 is a contactor coil command only. Motor power and overload protection are outside this drawing.', 3)
        power.text(18, 66, 'EStopOK and GuardClosed are simulated healthy contacts, not a safety-rated stop chain.', 3)
    else:
        for n, function in enumerate(['MASTER', 'PUMP', 'LIGHTS']):
            y = 175-n*28
            power.text(25,y,f'J1:{n+1} (+24 V)',3)
            power.line(90,y+1,140,y+1)
            power.text(145,y,f'S{n+1} {function}',3)
            power.line(205,y+1,240,y+1)
            power.text(245,y,f'H{n+1} indicator',3)
            power.line(302,y+1,330,y+1)
            power.text(336,y,f'J1:{n+4} (0 V)',3)
    power.text(18, 48, 'For each branch, use its wire IDs on the I/O sheet and full endpoint schedule.', 3)
    sheets.append(power)

    io = Sheet('02 / 24 V DC INPUT AND OUTPUT WIRING')
    mapped = [p for p in panel['pins'] if p.get('address')]
    io.text(18, 264, 'Each PLC address maps to one wired pin. Signal names match plc/line.xml.' if mapped else 'Three toggle switches and matching indicators. Each row identifies both connector pins and the cut wire.', 3)
    if mapped:
        for n, p in enumerate(mapped):
            y = 246 - n*13
            is_input = p['address'].startswith('%I')
            # Follow field wire from PLC pin through the two-sided terminal.
            plcwire = next(w for w in panel['wires'] if (w['from_device'], w['from_pin']) == (p['device'], p['pin']) or
                           (w['to_device'], w['to_pin']) == (p['device'], p['pin']))
            terminal = plcwire['from_device'] if plcwire['from_device'] != p['device'] else plcwire['to_device']
            fieldwire = next(w for w in panel['wires'] if w != plcwire and
                             (w['from_device'] == terminal or w['to_device'] == terminal))
            field = fieldwire['from_device'] if fieldwire['from_device'] != terminal else fieldwire['to_device']
            # Find supply/return leg so every cut wire appears in a circuit.
            supplywire = next(w for w in panel['wires'] if w != fieldwire and
                              (w['from_device'] == field or w['to_device'] == field))
            common = endpoint(supplywire, 'from' if supplywire['from_device'] != field else 'to')
            io.text(18, y-1, common, 2.6)
            io.line(48, y, 76, y)
            io.text(49, y+2, f"W{supplywire['wire']}", 2.5)
            io.rect(76, y-4, 36, 8)
            io.text(78, y-1, field, 3)
            # Simple contact/coil indication, with clear device ID outside.
            if is_input:
                io.line(112, y, 122, y)
                io.line(122, y, 133, y+3)
                io.line(136, y, 192, y)
            else:
                io.line(112, y, 123, y)
                io.rect(123, y-3, 12, 6)
                io.line(135, y, 192, y)
            io.text(149, y+2, f"W{fieldwire['wire']}", 2.5)
            io.rect(192, y-4, 35, 8)
            io.text(195, y-1, f'{terminal}:F/P', 2.6)
            io.line(227, y, 280, y)
            io.text(241, y+2, f"W{plcwire['wire']}", 2.5)
            io.rect(280, y-4, 47, 8)
            io.text(283, y-1, p['address'], 3)
            io.text(332, y-1, p['signal'], 3)
        io.text(18, 39, 'Inputs: +24 V -> contact -> X:F/P -> PLC. Outputs: PLC -> X:P/F -> coil/lamp -> 0 V.', 3)
    else:
        for n, w in enumerate(panel['wires']):
            y = 242 - n*19
            io.text(20, y, endpoint(w, 'from'), 3.5)
            io.line(95, y+1, 290, y+1)
            io.text(110, y+4, f"W{w['wire']} | {w['gauge']} {w['colour']} | {w['length_m']} m", 3)
            io.text(300, y, endpoint(w, 'to'), 3.5)
    sheets.append(io)

    schedule = terminal_schedule(panel)
    # Two columns, 40 rows each. Long schedules continue on another PDF page.
    for start in range(0, len(schedule), 80):
        terminal = Sheet('03 / TERMINAL AND WIRE SCHEDULE')
        for col in range(2):
            x = 18 + col*198
            terminal.text(x, 263, 'PIN', 3)
            terminal.text(x+52, 263, 'WIRE', 3)
            terminal.text(x+73, 263, 'OTHER END', 3)
            terminal.text(x+137, 263, 'COLOUR', 3)
            for n, r in enumerate(schedule[start+col*40:start+(col+1)*40]):
                y=254-n*5.3
                terminal.text(x,y,f"{r['device']}:{r['pin']}",2.7)
                terminal.text(x+52,y,r['wire'],2.7)
                terminal.text(x+73,y,r['destination'],2.7)
                terminal.text(x+137,y,r['colour'],2.7)
        terminal.text(18, 34, 'CSV and Excel schedules include PLC signal names, addresses and wire gauge.', 2.7)
        sheets.append(terminal)

    layout = Sheet('04 / CONTROL PANEL LAYOUT')
    layout.text(18, 262, '500 x 400 mm backplate study. Field sensors, contactor and valve are external.' if mapped else '500 x 400 mm cockpit-style faceplate study. Switches below indicators; harness connector at the rear.', 3)
    layout.text(18, 254, 'Coordinates and footprints come from devices.csv; dimensions are illustrative millimetres.', 3)
    # 0.42 scale gives a dimensioned backplate plus room for a legend.
    ox, oy, scale = 25, 65, .42
    layout.rect(ox, oy, 500*scale, 400*scale)
    layout.text(80, 51, '500 mm', 3.5)
    layout.text(240, 152, '400 mm', 3.5)
    for y in ((150, 300) if mapped else ()):
        layout.line(ox+8, oy+y*scale, ox+202, oy+y*scale)
    mounted = [d for d in panel['devices'] if d['mount']=='panel']
    for d in mounted:
        x=ox+float(d['x_mm'])*scale;y=oy+float(d['y_mm'])*scale
        layout.rect(x,y,float(d['width_mm'])*scale,float(d['height_mm'])*scale)
        layout.text(x+1.5,y+7,d['device'],2.6)
        if d.get('function'):
            layout.text(x,y-5,d['function'],2.8)
    layout.text(278, 228, 'PANEL REFERENCES', 3.5)
    for n,d in enumerate(mounted):
        layout.text(278,218-n*5.6,f"{d['device']}: {d['part']}",2.5)
    layout.text(18, 39, 'Reserve wiring ducts and clearances before any physical construction; no enclosure or heat study included.', 2.7)
    sheets.append(layout)

    totals = bom(panel)
    parts = Sheet('05 / CONSOLIDATED BILL OF MATERIALS')
    parts.text(18, 263, 'Device quantities are consolidated by part. Wire totals are cut lengths, without spare/waste allowance.', 3)
    for x,label in [(18,'PART'),(95,'DESCRIPTION'),(345,'QTY'),(380,'UNIT')]:parts.text(x,250,label,3)
    for n,r in enumerate(totals):
        y=239-n*8
        parts.text(18,y,r['item'],2.7)
        parts.text(95,y,r['description'],2.7)
        parts.text(345,y,str(r['quantity'].normalize()),2.7)
        parts.text(380,y,r['unit'],2.7)
    parts.text(18, 39, 'Generic study parts are not manufacturer selections; PLC-24 represents the simulated controller, not a selected commercial model.', 2.7)
    sheets.append(parts)
    for n,sheet in enumerate(sheets,1):sheet.frame(n)
    return sheets


def write_drawings(panel, dxf_path, pdf_path, title):
    import ezdxf
    from reportlab.pdfgen.canvas import Canvas
    from ezdxf.enums import TextEntityAlignment
    sheets = sheets_for(panel)
    doc = ezdxf.new('R2010', setup=True)
    doc.units = 4  # millimetres
    doc.layouts.rename('Layout1', 'Power')
    canvas = Canvas(str(pdf_path), pagesize=(WIDTH*MM, HEIGHT*MM), invariant=1)
    canvas.setTitle(title + ' control panel drawing set')
    canvas.setAuthor('Jack Lai')
    # All native editable sheets sit side by side in model space; four named
    # paper-space views make the requested drawing set easy to find in CAD.
    layout_names={'01': 'Power', '02': 'IO', '03': 'Terminals', '04': 'Layout', '05': 'BOM'}
    populated = defaultdict(int)
    for index, sheet in enumerate(sheets):
        layer=f'SHEET_{index+1}'
        doc.layers.new(layer)
        xoffset=index*440
        model=doc.modelspace()
        paper_name = layout_names.get(sheet.title[:2])
        populated[paper_name] += 1
        if populated[paper_name] > 1:
            paper_name += str(populated[paper_name])
        paper = doc.layouts.get('Power') if paper_name == 'Power' else doc.layouts.new(paper_name)
        paper.page_setup(size=(WIDTH, HEIGHT), margins=(0, 0, 0, 0), units='mm')
        canvas.setLineWidth(.6)
        for kind,args in sheet.shapes:
            if kind=='line':
                x1,y1,x2,y2=args
                canvas.line(x1*MM,y1*MM,x2*MM,y2*MM)
                model.add_line((x1+xoffset,y1),(x2+xoffset,y2),dxfattribs={'layer':layer})
                if paper is not None:paper.add_line((x1,y1),(x2,y2))
            elif kind=='rect':
                x,y,w,h=args
                canvas.rect(x*MM,y*MM,w*MM,h*MM)
                points=[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
                model.add_lwpolyline([(a+xoffset,b) for a,b in points],close=True,dxfattribs={'layer':layer})
                if paper is not None:paper.add_lwpolyline(points,close=True)
            else:
                x,y,text,size=args
                canvas.setFont('Helvetica',size*MM)
                canvas.drawString(x*MM,y*MM,text)
                model.add_text(text,dxfattribs={'height':size,'layer':layer}).set_placement((x+xoffset,y))
                if paper is not None:paper.add_text(text,dxfattribs={'height':size}).set_placement((x,y))
        canvas.showPage()
    canvas.save()
    # ezdxf auditing catches dangling handles and corrupt native entities.
    audit=doc.audit()
    if audit.has_errors:
        raise ValueError('Generated DXF failed audit')
    doc.saveas(dxf_path)
