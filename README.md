# ERP Platform Delivery Management — Odoo 18 Backend Assessment

## Giả định của bài làm (Assumptions)

Danh sách dưới đây là toàn bộ giả định dùng để chốt các điểm đề bài chưa quy định chi tiết. Mã `A-xx` được giữ ổn định để đối chiếu khi review và kiểm thử.

| Mã | Giả định đã chọn | Phần liên quan trong đề bài |
|---|---|---|
| A-01 | Tận dụng model chuẩn: khách hàng ERP mở rộng `res.partner`, dự án ERP mở rộng `project.project`, task dùng `project.task` và milestone dùng `project.milestone`; không tạo hệ thống song song. | Phần 1 - Kiến trúc giải pháp và khả năng tích hợp module; Phần 2 - Quản lý khách hàng ERP; Phần 4 - Quản lý dự án triển khai ERP; Phần 5 - Phân hệ triển khai, task, milestone và dữ liệu tính toán. |
| A-02 | Có hai cấp hợp đồng: thông tin trên `res.partner` là hợp đồng thuê bao nền tảng cấp khách hàng; `sale.order` là hợp đồng dịch vụ triển khai của từng dự án. Một khách hàng có thể có nhiều hợp đồng và dự án triển khai. | Phần 2 - Quản lý khách hàng ERP; Phần 4 - Quản lý dự án triển khai ERP; Phần 6 - Tích hợp Sales / hợp đồng. |
| A-03 | Contact thông thường có thể là global. ERP customer phải thuộc đúng một company; `ref_code` bắt buộc và chỉ unique trong company đó. | Phần 2 - Quản lý khách hàng ERP; Phần 8 - Phân quyền và Multi-company. |
| A-04 | Danh mục `erp.solution` là master data dùng chung giữa các company; riêng chi phí nội bộ và tiền tệ chi phí là dữ liệu phụ thuộc company. | Phần 3 - Danh mục giải pháp ERP; Phần 8 - Phân quyền và Multi-company. |
| A-05 | Một Sales Order chỉ tạo tối đa một ERP project. Khi tạo, dự án snapshot khách hàng, tổng tiền và tiền tệ nguồn; thay đổi đơn hàng về sau chỉ cập nhật dự án qua action đồng bộ tường minh. | Phần 4 - Quản lý dự án triển khai ERP; Phần 6 - Tích hợp Sales / hợp đồng. |
| A-06 | Khi cài Sales Integration, project có Sales Order liên kết chỉ được Go-live nếu order ở trạng thái `sale`, kể cả khi không cài Quality Gate. Khi cài cả Sales và Quality, hai nhóm blocker được cộng dồn bằng cooperative hook. | Phần 6 - Tích hợp Sales / hợp đồng; Phần 7 - Go-live và Quality Gate tùy chọn. |
| A-07 | Task bắt buộc chỉ hoàn thành khi ở trạng thái `1_done`; task bị hủy không được coi là hoàn thành. Milestone bắt buộc chỉ hoàn thành khi `is_reached=True`. | Phần 5 - Phân hệ triển khai, task, milestone và dữ liệu tính toán; Phần 7 - Go-live và Quality Gate tùy chọn. |
| A-08 | Thời lượng dự án là chênh lệch ngày, không tính gộp hai đầu mốc. Nếu payload đồng thời gửi thời lượng và ngày Go-live dự kiến không nhất quán, backend từ chối thay vì âm thầm ưu tiên một giá trị. | Phần 4 - Quản lý dự án triển khai ERP; Phần 5 - Phân hệ triển khai, task, milestone và dữ liệu tính toán. |
| A-09 | Health dùng độ lệch tiến độ kế hoạch: lớn hơn 20 điểm phần trăm là Red, từ 10 đến 20 là Amber, kết hợp rủi ro và item bắt buộc quá hạn. Health được lưu để tìm kiếm và được cron cập nhật hằng ngày. | Phần 5 - Phân hệ triển khai, task, milestone và dữ liệu tính toán; Phần 9 - Performance, ORM và khả năng mở rộng. |
| A-10 | Quality Score có thang 100 gồm task 50 điểm, risk 20 điểm, nghiệm thu phân hệ 20 điểm và checklist 10 điểm. Ngưỡng mặc định là 80 theo company; gate lưu snapshot phục vụ audit nhưng Go-live luôn kiểm tra lại dữ liệu hiện hành. | Phần 7 - Go-live và Quality Gate tùy chọn; Phần 8 - Phân quyền và Multi-company; Phần 9 - Performance, ORM và khả năng mở rộng. |

## Trạng thái repository

Ba custom addon ERP Delivery đã được triển khai trong `custom_addons`: `erp_delivery_management`, `erp_delivery_sale` và `erp_delivery_quality`. Source Python, XML và manifest đã được static-validate. Theo yêu cầu của bài làm, addon chưa được tự động cài vào database; backend tests đã được viết nhưng chưa runtime-verify trên một database Odoo.

## Kiến trúc mục tiêu

```text
base + mail + project
        |
        v
erp_delivery_management
        |-----------------------------|
        v                             v
erp_delivery_sale              erp_delivery_quality
sale_management                độc lập với Sales
```

- `erp_delivery_management`: customer, solution, project, project line, task, milestone, workflow, core Go-live, security và aggregates.
- `erp_delivery_sale`: tạo project từ confirmed Sales Order, liên kết hai chiều và commercial Go-live blocker.
- `erp_delivery_quality`: quality checklist, scoring, company threshold, evaluation history và quality Go-live blocker.

Core mở rộng `project.project`; không tạo model project song song. Task dùng `project.task`; milestone dùng `project.milestone`.

Giá trị hợp đồng dùng `contract_currency_id` riêng. Khi tạo từ Sales Order, hệ thống snapshot đồng thời tổng tiền và tiền tệ nguồn; thay đổi đơn hàng về sau không âm thầm ghi đè project.

## Cơ chế mở rộng Go-live

Core định nghĩa `_get_go_live_blockers()`. Sales và Quality cùng gọi `super()` và append blocker của mình. `action_go_live()` tổng hợp blocker, raise một lần nếu có lỗi, sau đó mới ghi state và actual Go-live date.

Sales sở hữu field/view hợp đồng. Quality không tham chiếu Sales, nên hai addon cài độc lập và không phụ thuộc thứ tự cài đặt.

## Multi-company và security

- ERP project/customer/line/gate bắt buộc có company.
- Solution là master dùng chung; internal cost và currency của cost là company-dependent. Về mặt kỹ thuật, Odoo ORM không cho phép `fields.Monetary` làm `company_dependent=True` (vì dữ liệu đa công ty được lưu dưới dạng cột `jsonb` trong PostgreSQL), do đó `internal_cost` sử dụng `fields.Float` kết hợp `digits="Product Price"` và `widget="monetary"` để vừa bảo đảm độ chính xác số học theo chuẩn hệ thống, vừa tuân thủ kiến trúc Odoo.
- Global company rules luôn giao với assignment rules.
- Consultant chỉ truy cập project mình là PM hoặc team member.
- Manager mở rộng phạm vi assignment trong allowed companies.
- Internal cost/subscription dùng Python field groups Manager-only.
- Contract value, line price và internal notes dùng Python field groups Consultant trở lên.
- Không dùng `sudo()` để né nghiệp vụ hoặc record rules.

## Quyết định về stored fields và hiệu năng

- `progress_percentage`, aggregate effort/count và `health_state` được lưu để list/search/group nhanh.
- Compute aggregate dùng `_read_group`/`read_group` trên toàn recordset, không search trong vòng lặp project.
- `health_state` phụ thuộc ngày hiện tại nên có cron daily batch recompute.
- Foreign keys và field search/group thường xuyên được index.
- Database constraints bảo vệ project-solution uniqueness và một project trên mỗi Sales Order.

Trade-off chính: stored aggregates tăng chi phí recompute khi nguồn thay đổi nhưng giảm đáng kể chi phí đọc danh sách lớn. Cron health tạo tải định kỳ nhưng tránh dữ liệu health lỗi thời.

## Tài liệu chuẩn

- Assessment gốc: `Odoo18_Backend_Assessment_ERP_Platform_FINAL (1).docx`
- Functional requirements: `docs/erp-delivery-management/erp-delivery-platform-functional-spec.md`
- Technical decisions: `TECHNICAL_DECISIONS.md`

## Test matrix bắt buộc

- Core only.
- Core + Sales.
- Core + Quality.
- Core + Sales + Quality.
- Workflow direct-write/RPC bypass attempts.
- Assigned/unassigned Consultant và Manager.
- Hai company, cross-company relation và company-dependent cost.
- Aggregates khi create/write/unlink nhiều records.
- Mandatory task cancelled không được coi là Done.
- Mandatory milestone chưa reached chặn Go-live.
- Duplicate project từ cùng Sales Order.
- Quality threshold/checklist và combined cooperative hook.
- Cron làm health thay đổi khi ngày trôi qua.

## Cách review

Reviewer dùng traceability matrix và chỉ đánh dấu `PASS` khi có code, security/UI tương ứng và backend tests. Tài liệu hoặc XML visibility không phải bằng chứng đủ cho correctness/security.
